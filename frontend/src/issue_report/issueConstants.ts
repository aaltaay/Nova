/** Filing an issue from the desk: the frontend's constants (backend: constants_issue_report.py). */
export const ISSUE_SCHEMA_VERSION = 1;
export const ISSUE_REPO = 'aaltaay/Nova';
export const ISSUE_NEW_URL = `https://github.com/${ISSUE_REPO}/issues/new`;
/** Mirrors ISSUE_REPORT_URL_BODY_MAX: GitHub refuses very long new-issue links. */
export const ISSUE_URL_BODY_MAX = 4000;
