export default {
  async fetch(request) {
    const url = new URL(request.url);
    const tweetPath = url.pathname.slice(1); // e.g. "NBCNews/status/123456"

    if (!tweetPath || tweetPath === "favicon.ico") {
      return new Response("Usage: /username/status/tweet_id", { status: 400 });
    }

    const apiResp = await fetch("https://api.fxtwitter.com/" + tweetPath);
    const data = await apiResp.json();

    return new Response(JSON.stringify(data), {
      headers: {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
      },
    });
  },
};
