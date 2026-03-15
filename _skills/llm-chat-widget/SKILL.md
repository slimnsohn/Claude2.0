# LLM Chat Widget

Drop-in Gemini-powered chat panel for any browser project. Zero dependencies, single script tag, client-side only.

## Integration

Add to any HTML page:

```html
<!-- Optional: configure before loading -->
<script>
  window.CHAT_WIDGET_CONFIG = {
    appName: "My App",                    // shown in chat header
    systemPrompt: "You are a ...",        // override default prompt
    contextFn: () => getAppState(),       // return live data as string
    welcomeMessage: "Ask me anything!",   // first chat bubble
    accentColor: "#58a6ff",               // theme color
    position: "bottom-right",             // bottom-right | bottom-left
  };
</script>

<!-- Load the widget -->
<script src="../../_skills/llm-chat-widget/dist/chat-widget.js"></script>
```

## How It Works

1. User clicks the floating chat bubble
2. On first use, prompts for Gemini API key (stored in sessionStorage — cleared on tab close)
3. Automatically reads page context: title, headings, tables, visible text
4. Sends context + question to Gemini API directly from the browser
5. Falls back through model tiers: `gemini-2.5-flash-lite` → `2.5-flash` → `2.0-flash-lite` → `2.0-flash`
6. Maintains conversation history within the session (last 20 turns)

## Context Customization

For richer answers, provide a `contextFn` that returns app-specific data:

```javascript
window.CHAT_WIDGET_CONFIG = {
  contextFn: () => JSON.stringify({
    currentView: app.view,
    filters: app.activeFilters,
    data: app.getVisibleRows(),
  }),
};
```

Without `contextFn`, the widget auto-discovers page content from the DOM.

## API Key

Uses `GEMINI_API_KEY`. The widget prompts on first use and stores in sessionStorage. No server, no `.env` file, no backend proxy needed. Key never leaves the browser except to Google's API.

## Files

- `dist/chat-widget.js` — The widget (~10KB, self-contained IIFE)
- `examples/basic.html` — Working demo page
