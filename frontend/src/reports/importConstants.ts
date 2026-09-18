/** Reports file import tunables (D-046 slice 3). Feature-local; not a barrel. */
export const JOURNAL_IMPORT_ACCEPT = '.csv,.json,text/csv,application/json';
export const JOURNAL_IMPORT_SAMPLE_NAME = 'nova-journal-sample.csv';
export const JOURNAL_IMPORT_SAMPLE_CSV =
  'symbol,side,qty,entry_price,exit_price,pnl,closed_at,commission,tags\n' +
  'IMP,long,100,10.00,10.50,48.00,2026-03-15,2.00,import;sample\n';
