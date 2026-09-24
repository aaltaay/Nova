/**
 * The issue form, mounted once in the main window's shell (not in Trader pop-outs). Opened by
 * `openIssueForm()` -- the What's new card's button, Help > File an Issue… -- and renders
 * nothing until then.
 */
import { IssueReportCard } from './IssueReportCard';
import { useIssueReport } from './useIssueReport';
import './issueReport.css';

export function IssueReportHost() {
  const report = useIssueReport();
  return <IssueReportCard r={report} />;
}
