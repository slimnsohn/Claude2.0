function parseTweetUrl(input) {
  var trimmed = input.trim();
  var match = trimmed.match(
    /(?:https?:\/\/)?(?:www\.)?(?:twitter\.com|x\.com)\/([^\/\s]+)\/status\/(\d+)/
  );
  if (match) return { user: match[1], id: match[2] };
  var idMatch = trimmed.match(/status\/(\d+)/);
  if (idMatch) return { user: "i", id: idMatch[1] };
  return null;
}

var PROXIES = [
  function(url) { return "https://api.allorigins.win/raw?url=" + encodeURIComponent(url); },
  function(url) { return "https://corsproxy.io/?" + encodeURIComponent(url); }
];

async function fetchTweetText(user, id) {
  var apiUrl = "https://api.fxtwitter.com/" + user + "/status/" + id;
  var lastErr = null;

  for (var p = 0; p < PROXIES.length; p++) {
    var proxyUrl = PROXIES[p](apiUrl);
    for (var attempt = 0; attempt < 2; attempt++) {
      try {
        var resp = await fetch(proxyUrl);
        if (resp.ok) {
          var data = await resp.json();
          var tweet = data.tweet;
          if (!tweet || !tweet.author) {
            throw new Error("No tweet data in response");
          }
          var text = tweet.text;
          if (!text && tweet.article) {
            text = tweet.article.title + "\n\n" + tweet.article.preview_text;
          }
          return {
            text: text || "No text found",
            authorName: tweet.author.name,
            authorHandle: tweet.author.screen_name,
          };
        }
      } catch (e) {
        lastErr = e;
      }
      if (attempt < 1) await new Promise(function(r) { setTimeout(r, 300); });
    }
  }
  throw lastErr || new Error("All proxies failed");
}

var urlInput = document.getElementById("url-input");
var fetchBtn = document.getElementById("fetch-btn");
var errorMsg = document.getElementById("error-msg");
var resultSection = document.getElementById("result-section");
var authorName = document.getElementById("author-name");
var authorHandle = document.getElementById("author-handle");
var tweetText = document.getElementById("tweet-text");
var copyBtn = document.getElementById("copy-btn");
var clearBtn = document.getElementById("clear-btn");
var copyConfirm = document.getElementById("copy-confirm");

function showError(msg) {
  errorMsg.textContent = msg;
  errorMsg.hidden = false;
}

function hideError() {
  errorMsg.hidden = true;
}

function showResult(data) {
  authorName.textContent = data.authorName;
  authorHandle.textContent = "@" + data.authorHandle;
  tweetText.textContent = data.text;
  resultSection.hidden = false;
}

function resetToInput() {
  resultSection.hidden = true;
  copyConfirm.hidden = true;
  urlInput.value = "";
  urlInput.focus();
  hideError();
}

async function handleFetch() {
  hideError();
  var parsed = parseTweetUrl(urlInput.value);
  if (!parsed) {
    showError("That doesn't look like a tweet link");
    return;
  }

  fetchBtn.disabled = true;
  urlInput.disabled = true;
  fetchBtn.textContent = "Loading...";

  try {
    var data = await fetchTweetText(parsed.user, parsed.id);
    showResult(data);
  } catch (err) {
    if (!navigator.onLine) {
      showError("No internet connection");
    } else {
      showError("Error: " + err.message);
    }
  } finally {
    fetchBtn.disabled = false;
    urlInput.disabled = false;
    fetchBtn.textContent = "Get Text";
  }
}

async function handleCopy() {
  try {
    await navigator.clipboard.writeText(tweetText.textContent);
    copyConfirm.hidden = false;
    setTimeout(function() { copyConfirm.hidden = true; }, 2000);
  } catch (e) {
    var range = document.createRange();
    range.selectNodeContents(tweetText);
    var sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
    document.execCommand("copy");
    copyConfirm.hidden = false;
    setTimeout(function() { copyConfirm.hidden = true; }, 2000);
  }
}

// Auto-fetch after paste — also listen for input change as fallback
urlInput.addEventListener("paste", function() {
  setTimeout(function() {
    if (urlInput.value && parseTweetUrl(urlInput.value)) {
      handleFetch();
    }
  }, 200);
});
urlInput.addEventListener("input", function() {
  if (urlInput.value && parseTweetUrl(urlInput.value)) {
    setTimeout(function() { handleFetch(); }, 100);
  }
});

fetchBtn.addEventListener("click", handleFetch);
urlInput.addEventListener("keydown", function(e) {
  if (e.key === "Enter") handleFetch();
});
copyBtn.addEventListener("click", handleCopy);
clearBtn.addEventListener("click", resetToInput);

urlInput.focus();
