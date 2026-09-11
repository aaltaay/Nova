"""Nova News admits AI-in-trading stories and drops AI-as-a-hot-stock."""
from __future__ import annotations

from nova_news.topic import is_ai_trading_story, topic_tags


def test_admits_ai_doing_the_trading():
    assert is_ai_trading_story(
        "Citadel expands its AI trading desk",
        "The hedge fund is using models to place orders.",
    )
    assert is_ai_trading_story(
        "Quant fund rolls out an execution algorithm",
        "",
    )
    assert is_ai_trading_story(
        "Autonomous trading bots hit a new high-water mark",
        "Retail flow followed the bots.",
    )


def test_rejects_ai_as_a_hot_stock_and_generic_tape():
    assert not is_ai_trading_story(
        "Nvidia share price soars on AI chip demand",
        "Wall Street analysts see a higher target.",
    )
    assert not is_ai_trading_story(
        "Fed holds rates as Wall Street waits",
        "Futures were little changed.",
    )
    assert not is_ai_trading_story(
        "Best AI stocks to buy now",
        "Motley Fool lists five names.",
    )


def test_headline_must_pair_ai_and_markets_unless_high_signal():
    assert is_ai_trading_story(
        "Machine learning comes to the trading desk",
        "A vendor note.",
    )
    assert not is_ai_trading_story(
        "OpenAI launches a new chatbot",
        "The model writes emails. A hedge fund is mentioned in paragraph 12.",
    )


def test_topic_tags_mark_executes_funds_and_research():
    tags = topic_tags(
        "AI hedge fund publishes an arXiv trading algorithm",
        "Systematic trading paper.",
        url="https://arxiv.org/abs/2601.00001",
        source="arXiv",
    )
    assert "executes" in tags
    assert "funds" in tags
    assert "research" in tags


def test_search_feeds_aim_at_ai_trading_not_generic_tape():
    from constants import NOVA_NEWS_SEARCH_FEEDS

    blobs = " ".join(url for _fid, _label, url in NOVA_NEWS_SEARCH_FEEDS).lower()
    assert "ai+trading" in blobs or "ai+hedge" in blobs
    assert "algorithmic+trading" in blobs
    assert "stock+or+markets+or" not in blobs
