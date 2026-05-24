/*
  Example shape for replacing a demo provider with a real scraper/API.

  Keep each provider isolated. A real adapter should:
  - respect the provider's terms and robots policy
  - prefer official or affiliate APIs
  - avoid bypassing CAPTCHA, login walls, Cloudflare, or other access controls
  - return the normalized offer shape used by searchEngine.js
*/

export function createLiveProviderAdapter({ name }) {
  return {
    name,
    mode: 'live',
    async search(query) {
      // Example:
      // const page = await browser.newPage();
      // await page.goto(buildProviderSearchUrl(query), { waitUntil: 'domcontentloaded' });
      // const offers = await extractVisibleFlightOffers(page);
      // return offers.map(normalizeProviderOffer);
      throw new Error(`${name} live adapter is not implemented yet.`);
    }
  };
}
