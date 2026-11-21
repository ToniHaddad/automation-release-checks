/**
 * Weekly recap of overdue and pending items. Synthetic example.
 */
function weeklyRecap() {
  const props = PropertiesService.getScriptProperties();
  const to = props.getProperty("RECAP_TO");
  const rows = SpreadsheetApp.getActive().getSheetByName("Premises").getDataRange().getValues();
  const today = new Date();
  const overdue = rows.slice(1).filter(function (r) {
    return r[5] instanceof Date && r[5] < today;
  });
  const missing = rows.slice(1).filter(function (r) {
    return !(r[4] instanceof Date) || !(r[5] instanceof Date);
  });
  const body = "Yearly end date already past: " + overdue.length + "\n" +
               "Rows with a missing date: " + missing.length;
  MailApp.sendEmail(to, "Weekly rental recap", body);
}
