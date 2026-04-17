// ---- Configuration ----
function getSheet(name) {
  return SpreadsheetApp.getActiveSpreadsheet().getSheetByName(name);
}

function checkAuth(e) {
  var token = '';
  if (e && e.parameter && e.parameter.token) {
    token = e.parameter.token;
  }
  if (e && e.postData) {
    try {
      var body = JSON.parse(e.postData.contents);
      if (body.token) token = body.token;
    } catch(err) {}
  }
  var expected = PropertiesService.getScriptProperties().getProperty('AUTH_TOKEN');
  if (token !== expected) {
    return false;
  }
  return true;
}

function jsonResponse(data) {
  return ContentService.createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}

function errorResponse(msg) {
  return jsonResponse({ ok: false, error: msg });
}

// ---- Bootstrap ----
function doGet(e) {
  if (!checkAuth(e)) return errorResponse('Unauthorized');

  var roomsSheet = getSheet('Rooms');
  var itemsSheet = getSheet('Items');
  var catsSheet = getSheet('Categories');

  var rooms = sheetToObjects(roomsSheet);
  var items = sheetToObjects(itemsSheet);
  var categories = sheetToObjects(catsSheet);

  return jsonResponse({ ok: true, rooms: rooms, items: items, categories: categories });
}

function sheetToObjects(sheet) {
  if (!sheet) return [];
  var data = sheet.getDataRange().getValues();
  if (data.length < 2) return [];
  var headers = data[0].map(function(h) { return h.toString().trim(); });
  var rows = [];
  for (var i = 1; i < data.length; i++) {
    var obj = {};
    for (var j = 0; j < headers.length; j++) {
      var val = data[i][j];
      if (val instanceof Date) {
        val = val.toISOString();
      }
      obj[headers[j]] = val;
    }
    rows.push(obj);
  }
  return rows;
}

// ---- Mutations ----
function doPost(e) {
  if (!checkAuth(e)) return errorResponse('Unauthorized');

  var body;
  try {
    body = JSON.parse(e.postData.contents);
  } catch(err) {
    return errorResponse('Invalid JSON');
  }

  var action = body.action;
  switch(action) {
    case 'create_item': return createItem(body);
    case 'update_item': return updateItem(body);
    case 'delete_item': return deleteItem(body);
    case 'bulk_update_items': return bulkUpdateItems(body);
    default: return errorResponse('Unknown action: ' + action);
  }
}

function createItem(body) {
  var item = body.item;
  if (!item || !item.room_id || !item.description) {
    return errorResponse('Missing required fields: room_id, description');
  }

  var sheet = getSheet('Items');
  var headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  var now = new Date().toISOString();

  var row = headers.map(function(h) {
    h = h.toString().trim();
    if (h === 'item_id') return item.item_id || Utilities.getUuid();
    if (h === 'created_at') return now;
    if (h === 'updated_at') return now;
    return item[h] !== undefined ? item[h] : '';
  });

  sheet.appendRow(row);
  return jsonResponse({ ok: true, item_id: row[headers.indexOf('item_id')] });
}

function updateItem(body) {
  var itemId = body.item_id;
  var fields = body.fields;
  if (!itemId || !fields) return errorResponse('Missing item_id or fields');

  var sheet = getSheet('Items');
  var data = sheet.getDataRange().getValues();
  var headers = data[0].map(function(h) { return h.toString().trim(); });
  var idCol = headers.indexOf('item_id');
  if (idCol === -1) return errorResponse('item_id column not found');

  for (var i = 1; i < data.length; i++) {
    if (data[i][idCol].toString() === itemId.toString()) {
      for (var key in fields) {
        var col = headers.indexOf(key);
        if (col !== -1 && key !== 'item_id' && key !== 'created_at') {
          sheet.getRange(i + 1, col + 1).setValue(fields[key]);
        }
      }
      var updCol = headers.indexOf('updated_at');
      if (updCol !== -1) {
        sheet.getRange(i + 1, updCol + 1).setValue(new Date().toISOString());
      }
      return jsonResponse({ ok: true });
    }
  }
  return errorResponse('Item not found: ' + itemId);
}

function deleteItem(body) {
  var itemId = body.item_id;
  if (!itemId) return errorResponse('Missing item_id');

  var sheet = getSheet('Items');
  var data = sheet.getDataRange().getValues();
  var headers = data[0].map(function(h) { return h.toString().trim(); });
  var idCol = headers.indexOf('item_id');
  if (idCol === -1) return errorResponse('item_id column not found');

  for (var i = 1; i < data.length; i++) {
    if (data[i][idCol].toString() === itemId.toString()) {
      sheet.deleteRow(i + 1);
      return jsonResponse({ ok: true });
    }
  }
  return errorResponse('Item not found: ' + itemId);
}

function bulkUpdateItems(body) {
  var itemIds = body.item_ids;
  var fields = body.fields;
  if (!itemIds || !itemIds.length || !fields) {
    return errorResponse('Missing item_ids or fields');
  }

  var sheet = getSheet('Items');
  var data = sheet.getDataRange().getValues();
  var headers = data[0].map(function(h) { return h.toString().trim(); });
  var idCol = headers.indexOf('item_id');
  if (idCol === -1) return errorResponse('item_id column not found');

  var idSet = {};
  for (var k = 0; k < itemIds.length; k++) {
    idSet[itemIds[k].toString()] = true;
  }

  var updated = 0;
  for (var i = 1; i < data.length; i++) {
    if (idSet[data[i][idCol].toString()]) {
      for (var key in fields) {
        var col = headers.indexOf(key);
        if (col !== -1 && key !== 'item_id' && key !== 'created_at') {
          sheet.getRange(i + 1, col + 1).setValue(fields[key]);
        }
      }
      var updCol = headers.indexOf('updated_at');
      if (updCol !== -1) {
        sheet.getRange(i + 1, updCol + 1).setValue(new Date().toISOString());
      }
      updated++;
    }
  }
  return jsonResponse({ ok: true, updated: updated });
}
