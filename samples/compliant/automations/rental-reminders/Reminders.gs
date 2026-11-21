/**
 * Rental contract reminders. Synthetic example.
 * Reads the "Premises" sheet and emails a reminder three months before a
 * contract ends and three months before the yearly period ends.
 * Recipients come from the Script Property REMINDER_TO (comma separated).
 */
const SHEET_NAME = "Premises";
const COL = {centre: 0, ref: 1, location: 2, owner: 3, contractEnd: 4, yearlyEnd: 5,
             followUp: 6, rent: 7, budget: 8};

function sendReminders() {
  const props = PropertiesService.getScriptProperties();
  const to = props.getProperty("REMINDER_TO");
  const rows = SpreadsheetApp.getActive().getSheetByName(SHEET_NAME).getDataRange().getValues();
  const today = new Date();
  const lines = [];
  rows.slice(1).forEach(function (r) {
    const contractEnd = r[COL.contractEnd];
    const yearlyEnd = r[COL.yearlyEnd];
    if (isDue_(contractEnd, today)) {
      lines.push(r[COL.centre] + " (" + r[COL.ref] + "): contract ends " + fmt_(contractEnd));
    }
    if (isDue_(yearlyEnd, today)) {
      lines.push(r[COL.centre] + " (" + r[COL.ref] + "): confirm next year's budget (" + r[COL.budget] + ")");
    }
  });
  if (lines.length === 0) return;
  MailApp.sendEmail(to, "Rental reminders: " + lines.length + " item(s)", lines.join("\n"));
}

function isDue_(date, today) {
  if (!(date instanceof Date)) return false;
  const limit = new Date(today.getFullYear(), today.getMonth() + 3, today.getDate());
  return date >= today && date <= limit;
}

function fmt_(date) {
  return Utilities.formatDate(date, "Asia/Beirut", "yyyy-MM-dd");
}
