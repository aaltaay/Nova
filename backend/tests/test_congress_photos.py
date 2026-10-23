"""ADR 066 decision 4: every member's portrait from one source, the Biographical Directory of the United States
Congress, shrunk to a face and asked for while the reports are still being read."""
import io
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
import requests
from PIL import Image

from congress import consent, photos, refresh
from congress.constants_congress import (
    CONGRESS_PHOTO_MAX_AGE_SEC,
    CONGRESS_PHOTO_RETRY_SEC,
    CONGRESS_PHOTO_URL,
    CONGRESS_RETRY_SEC,
    CONGRESS_SESSION_GAP_SEC,
)
from congress.state import source
from tests.test_congress_reader import SATURDAY, UUID_E, FakeNet, Resp, net, portrait, run_all  # noqa: F401

MONDAY_10 = datetime(2026, 10, 19, 10, 0, tzinfo=ZoneInfo("America/New_York")).timestamp()


class PhotoNet:
    """The Bioguide alone: one answer per bioguide id, 404 for any other."""

    def __init__(self, **answers):
        self.answers, self.calls = answers, []

    def get(self, url, **kw):
        self.calls.append(url)
        answer = self.answers.get(url.rsplit("/", 1)[-1].removesuffix(".jpg"), Resp(404))
        if isinstance(answer, Exception):
            raise answer
        return answer


def test_a_portrait_comes_from_the_bioguide_alone_and_is_kept_as_a_face():
    fake = PhotoNet(S000001=Resp(content=portrait()))
    assert photos.fetch(fake, "S000001", SATURDAY) is True
    assert fake.calls == [CONGRESS_PHOTO_URL.format(bioguide="S000001")]
    assert fake.calls == ["https://bioguide.congress.gov/photo/S000001.jpg"]
    assert photos.kept() == {"S000001"}
    with Image.open(photos.kept_file("S000001")) as face:
        assert face.format == "JPEG" and face.size == (240, 300)


def test_a_small_portrait_is_kept_as_it_is_drawn():
    assert photos.fetch(PhotoNet(S000001=Resp(content=portrait((180, 225)))), "S000001", SATURDAY) is True
    with Image.open(photos.kept_file("S000001")) as face:
        assert face.size == (180, 225)


def test_a_member_the_bioguide_has_no_portrait_for_is_asked_again_after_a_day():
    fake = PhotoNet(S000002=Resp(content=b"<html>not a picture</html>"))
    assert photos.fetch(fake, "S000001", SATURDAY) is False                      # 404
    assert photos.fetch(fake, "S000002", SATURDAY) is False                      # 200, but no JPEG
    assert photos.kept() == set() and photos.kept_file("S000001") is None
    assert photos.wanted(["S000001", "S000002"], SATURDAY + CONGRESS_PHOTO_RETRY_SEC - 1) == []
    assert photos.wanted(["S000001", "S000002"], SATURDAY + CONGRESS_PHOTO_RETRY_SEC) == ["S000001", "S000002"]


def test_a_picture_declaring_too_many_pixels_is_never_decoded(monkeypatch):
    monkeypatch.setattr(photos, "CONGRESS_MAX_PHOTO_PIXELS", 1000)
    assert photos.fetch(PhotoNet(S000001=Resp(content=portrait())), "S000001", SATURDAY) is False
    assert photos.kept() == set()


def test_the_site_failing_is_raised_and_never_counted_as_the_members_miss():
    fake = PhotoNet(S000001=Resp(503), S000002=requests.ConnectionError("reset"))
    with pytest.raises(requests.HTTPError):
        photos.fetch(fake, "S000001", SATURDAY)
    with pytest.raises(requests.ConnectionError):
        photos.fetch(fake, "S000002", SATURDAY)
    assert photos.wanted(["S000001", "S000002"], SATURDAY) == ["S000001", "S000002"]


def test_a_portrait_kept_from_another_source_is_asked_for_again():
    photos.file("S000001").write_bytes(portrait((225, 275)))                     # unitedstates/images, before
    (photos.folder() / "misses.json").write_text(json.dumps({"schema_version": 1, "misses": {"S000002": SATURDAY}}))
    assert photos.kept() == set() and photos.kept_file("S000001") is None
    assert photos.wanted(["S000001", "S000002"], SATURDAY) == ["S000001", "S000002"]
    (photos.folder() / "index.json").write_text(json.dumps(
        {"schema_version": 2, "source": "https://example.org/{bioguide}.jpg", "kept": {"S000001": SATURDAY}}))
    assert photos.kept() == set()                                                # an index of another source
    assert photos.fetch(PhotoNet(S000001=Resp(content=portrait())), "S000001", SATURDAY) is True
    assert photos.kept() == {"S000001"}


def test_a_kept_portrait_is_asked_again_after_a_month_after_the_new_ones():
    photos.fetch(PhotoNet(S000001=Resp(content=portrait())), "S000001", SATURDAY)
    assert photos.wanted(["S000001", "H000001"], SATURDAY + CONGRESS_PHOTO_MAX_AGE_SEC - 1) == ["H000001"]
    later = SATURDAY + CONGRESS_PHOTO_MAX_AGE_SEC
    assert photos.wanted(["S000001", "H000001"], later) == ["H000001", "S000001"]
    assert photos.fetch(PhotoNet(), "S000001", later) is False                   # gone from the Bioguide: kept, not asked
    assert photos.kept() == {"S000001"} and photos.wanted(["S000001"], later + 1) == []


def test_portraits_arrive_while_the_reports_are_still_read(net):
    consent.accept(SATURDAY)
    run_all()
    urls = [u for _, u in net.calls]
    first_face = next(i for i, u in enumerate(urls) if u.startswith("https://bioguide.congress.gov/photo/"))
    assert first_face < urls.index(next(u for u in urls if f"/ptr/{UUID_E}" in u))  # a report was still unread
    assert source("photos").state == "ok" and photos.kept() == {"S000001"}       # H000001: none in the fake


class BioguideDown(FakeNet):
    def _answer(self, method, url, kw):
        if "bioguide.congress.gov" in url:
            self.calls.append((method, url))
            return Resp(503)
        return super()._answer(method, url, kw)


def test_the_bioguide_failing_pauses_every_portrait_not_one_a_second(monkeypatch):
    from congress import house_pdf

    monkeypatch.setattr(house_pdf, "pdf_text", lambda data: data.decode())
    fake = BioguideDown()
    refresh.reset_for_tests(fake)
    consent.accept(SATURDAY)
    run_all()
    asked = [u for _, u in fake.calls if "bioguide.congress.gov" in u]
    assert len(asked) == 1                                                       # once, then the source waits
    assert source("photos").state == "failing" and "503" in source("photos").error
    assert source("photos").next_at == SATURDAY + CONGRESS_RETRY_SEC
    assert refresh.run_once(SATURDAY + CONGRESS_RETRY_SEC - 1) is False
    refresh.run_once(SATURDAY + CONGRESS_RETRY_SEC)
    assert len([u for _, u in fake.calls if "bioguide.congress.gov" in u]) == 2


def test_in_the_session_a_portrait_waits_the_same_gap_as_a_report(net):
    consent.accept(MONDAY_10)
    for _ in range(20):                                                          # everything due at one moment
        if not refresh.run_once(MONDAY_10):
            break
    downloads = [u for _, u in net.calls if u.endswith(".pdf") or "/ptr/" in u or "bioguide.congress.gov" in u]
    assert len(downloads) == 1
    refresh.run_once(MONDAY_10 + CONGRESS_SESSION_GAP_SEC)
    downloads = [u for _, u in net.calls if u.endswith(".pdf") or "/ptr/" in u or "bioguide.congress.gov" in u]
    assert len(downloads) == 2
