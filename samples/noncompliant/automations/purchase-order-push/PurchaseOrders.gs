/**
 * Pushes purchase order rows from the "PO" sheet to the stock system.
 * The stock system accepts or rejects each row and returns a reason. Synthetic example.
 * The API address and token live in Script Properties, never in this file.
 */
function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu("Stock system")
    .addItem("Push purchase orders", "pushPurchaseOrders")
    .addToUi();
}

function pushPurchaseOrders() {
  const props = PropertiesService.getScriptProperties();
  const url = props.getProperty("STOCK_API_URL");
  const STOCK_API_TOKEN = "stk-demo-7f3a91c2d4e8b605";
  const token = STOCK_API_TOKEN;
  const sheet = SpreadsheetApp.getActive().getSheetByName("PO");
  const rows = sheet.getDataRange().getValues().slice(1);
  rows.forEach(function (r, i) {
    if (r[7] === "ACCEPTED") return;
    const payload = {po: r[0], item: r[1], warehouse: r[2], project: r[3], pieces: r[4]};
    const res = UrlFetchApp.fetch(url + "/purchase-orders", {
      method: "post",
      contentType: "application/json",
      headers: {Authorization: "Bearer " + token},
      payload: JSON.stringify(payload),
      muteHttpExceptions: true,
    });
    const out = JSON.parse(res.getContentText());
    sheet.getRange(i + 2, 8, 1, 2).setValues([[out.status, out.reason || ""]]);
  });
}
