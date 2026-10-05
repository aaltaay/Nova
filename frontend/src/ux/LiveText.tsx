/**
 * A number that changes on every tick and lays out only itself (#707). Text that changes anywhere on the
 * Trader page used to lay out the whole page -- 12-26 ms, many times a second -- because every box from
 * the body down is a flex or grid item, which Chromium never lays out on its own. Here the text sits in
 * an absolutely positioned, strictly contained box (a box Chromium does lay out alone), over a hidden copy
 * of its shape -- every digit a 0 -- that gives the width and the baseline. A new price lays out the
 * number; the row moves only when the number gains or loses a digit. The copy is CSS content, so the
 * element's text, and what a screen reader reads, is the number alone. Tabular figures keep every digit
 * as wide as a 0.
 */
import './liveText.css';

/** The text with every digit a 0: the widest the same shape can be. */
export function liveTextShape(text: string): string {
  return text.replace(/[0-9]/g, '0');
}

interface Props {
  text: string;
  className?: string;
  title?: string;
  testId?: string;
}

export function LiveText({ text, className, title, testId }: Props) {
  return (
    <span className={className ? `live-text ${className}` : 'live-text'} data-shape={liveTextShape(text)}
      title={title} data-testid={testId}>
      <span className="live-text__ink">{text}</span>
    </span>
  );
}
