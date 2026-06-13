// === CONFIGURATION ===
const SPREADSHEET_ID = '1Ss7t2knbX3JzNR4QnJZHw3z-xbZwW3m4mFFZnsvRdPg';

function getCurrentSheetName() {
  var now = new Date();
  return now.getFullYear() + '_' + (now.getMonth() + 1);
}

// Column mappings (1-indexed)
// SS: date=N(14), amt=O(15), src_dst=P(16)
// NK: date=Q(17), amt=R(18), book=S(19)
const COLUMNS = {
  SS: { date: 14, amt: 15, book: 16 },
  NK: { date: 17, amt: 18, book: 19 }
};

// Row where data starts (after headers)
const DATA_START_ROW = 4;

function doGet() {
  return HtmlService.createHtmlOutputFromFile('Index')
    .setTitle('Sportsbook Logger')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no');
}

function getMonthSheet(spreadsheet) {
  var name = getCurrentSheetName();
  var sheet = spreadsheet.getSheetByName(name);
  if (!sheet) return null;
  return sheet;
}

// Whitelist of valid inputs
const VALID_USERS = ['SS', 'NK'];
const VALID_BOOKS = ['bo', 'bk', 'nv', 'px', 'py', 'fd', 'ci', 'cs', 'ka'];
const MAX_AMOUNT = 500000;

function addEntry(user, date, amount, book) {
  // === SERVER-SIDE VALIDATION ===
  
  // Validate user
  if (VALID_USERS.indexOf(user) === -1) {
    return { success: false, error: 'Invalid user' };
  }
  
  // Validate book
  if (VALID_BOOKS.indexOf(String(book).toLowerCase()) === -1) {
    return { success: false, error: 'Invalid book' };
  }
  
  // Validate amount: must be a finite number, non-zero, within bounds
  var numAmount = Number(amount);
  if (!isFinite(numAmount) || numAmount === 0 || Math.abs(numAmount) > MAX_AMOUNT) {
    return { success: false, error: 'Invalid amount' };
  }
  // Force integer (no fractional cents)
  numAmount = Math.round(numAmount);
  
  // Validate date format: must match M/D or MM/DD pattern
  var dateStr = String(date).trim();
  if (!/^\d{1,2}\/\d{1,2}$/.test(dateStr)) {
    return { success: false, error: 'Invalid date format (use M/D)' };
  }
  // Validate date values are sane
  var dateParts = dateStr.split('/');
  var month = parseInt(dateParts[0]);
  var day = parseInt(dateParts[1]);
  if (month < 1 || month > 12 || day < 1 || day > 31) {
    return { success: false, error: 'Invalid date values' };
  }
  
  // Sanitize book to lowercase
  var cleanBook = String(book).toLowerCase().trim();
  
  // === WRITE TO SHEET ===
  var ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  var sheet = getMonthSheet(ss);
  
  if (!sheet) {
    return { success: false, error: 'Sheet not found' };
  }
  
  var cols = COLUMNS[user];
  
  // Find the next empty row for this user's section
  var dateCol = cols.date;
  var lastRow = sheet.getLastRow();
  var nextRow = DATA_START_ROW;
  
  // Scan down the date column to find first empty cell
  if (lastRow >= DATA_START_ROW) {
    var dateRange = sheet.getRange(DATA_START_ROW, dateCol, lastRow - DATA_START_ROW + 1, 1).getValues();
    for (var i = 0; i < dateRange.length; i++) {
      if (dateRange[i][0] === '' || dateRange[i][0] === null) {
        nextRow = DATA_START_ROW + i;
        break;
      }
      nextRow = DATA_START_ROW + i + 1;
    }
  }
  
  // Write the validated/sanitized data
  sheet.getRange(nextRow, cols.date).setValue(dateStr);
  sheet.getRange(nextRow, cols.amt).setValue(numAmount);
  sheet.getRange(nextRow, cols.book).setValue(cleanBook);
  
  return { 
    success: true, 
    row: nextRow, 
    message: user + ': ' + (numAmount > 0 ? '+' : '') + numAmount + ' @ ' + cleanBook + ' (' + dateStr + ')' 
  };
}

function getRecentEntries(user, count) {
  var ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  var sheet = getMonthSheet(ss);
  
  if (!sheet) return [];
  
  var cols = COLUMNS[user];
  var lastRow = sheet.getLastRow();
  var entries = [];
  
  if (lastRow >= DATA_START_ROW) {
    var range = sheet.getRange(DATA_START_ROW, cols.date, lastRow - DATA_START_ROW + 1, 3).getValues();
    for (var i = range.length - 1; i >= 0 && entries.length < count; i--) {
      if (range[i][0] !== '' && range[i][0] !== null) {
        entries.push({
          date: range[i][0],
          amt: range[i][1],
          book: range[i][2]
        });
      }
    }
  }
  
  return entries;
}

function getBalances() {
  var ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  var sheet = getMonthSheet(ss);
  
  if (!sheet) return { SS: 0, NK: 0 };
  
  // Row 2 has the running totals — adjust if different
  // SS total is in column O (15), NK total is in column R (18)
  var ssBalance = sheet.getRange(2, 15).getValue();
  var nkBalance = sheet.getRange(2, 18).getValue();
  
  return { SS: ssBalance, NK: nkBalance };
}
