import { test, expect } from '@playwright/test';

test('investigate volume sorting discrepancy', async ({ page }) => {
  // Capture all API responses
  const apiResponses: any[] = [];
  page.on('response', async (response) => {
    if (response.url().includes('/api/markets')) {
      try {
        const data = await response.json();
        apiResponses.push({
          url: response.url(),
          data: data
        });
      } catch (e) {}
    }
  });

  await page.goto('/');
  await page.waitForSelector('table');

  // Wait for initial data load
  await page.waitForTimeout(2000);

  // Get the first 10 markets displayed in the UI
  console.log('\n=== TOP 10 MARKETS IN UI (by default volume sort) ===\n');

  const rows = page.locator('tbody tr');
  const rowCount = await rows.count();

  for (let i = 0; i < Math.min(10, rowCount); i++) {
    const row = rows.nth(i);
    // Skip virtual spacer rows
    const text = await row.textContent();
    if (!text || text.trim().length < 10) continue;

    // Get all cell contents
    const cells = row.locator('td');
    const cellCount = await cells.count();

    const cellTexts: string[] = [];
    for (let j = 0; j < cellCount; j++) {
      const cellText = await cells.nth(j).textContent();
      cellTexts.push(cellText?.trim() || '');
    }

    console.log(`Row ${i}: ${cellTexts.join(' | ')}`);
  }

  // Now check the raw API response
  console.log('\n=== API RESPONSE DATA ===\n');

  if (apiResponses.length > 0) {
    const firstResponse = apiResponses[0];
    console.log('API URL:', firstResponse.url);
    console.log('Total markets:', firstResponse.data?.total);
    console.log('\nFirst 10 markets from API:');

    const items = firstResponse.data?.items || [];
    for (let i = 0; i < Math.min(10, items.length); i++) {
      const market = items[i];
      console.log(`\n${i + 1}. ${market.question?.substring(0, 60)}...`);
      console.log(`   Volume 24h: ${market.liquidity?.volume_24h}`);
      console.log(`   Volume 7d: ${market.liquidity?.volume_7d}`);
      console.log(`   Liquidity Score: ${market.liquidity?.liquidity_score}`);
      console.log(`   Category: ${market.category}`);
    }
  }

  // Direct API call to compare
  console.log('\n=== DIRECT CURL COMPARISON ===\n');
});

test('check volume data types and sorting', async ({ page, request }) => {
  // Make direct API request
  const response = await request.get('http://localhost:8000/api/markets?sort_by=volume_24h&sort_desc=true&page_size=20');
  const data = await response.json();

  console.log('\n=== DIRECT API: Top 20 by volume_24h ===\n');

  const items = data.items || [];
  for (let i = 0; i < items.length; i++) {
    const market = items[i];
    const vol24h = market.liquidity?.volume_24h;
    const vol24hNum = parseFloat(vol24h || '0');

    console.log(`${i + 1}. Vol: ${vol24hNum.toLocaleString()} | ${market.question?.substring(0, 50)}...`);
  }

  // Check if volumes are actually sorted correctly
  console.log('\n=== VOLUME SORT CHECK ===\n');

  let prevVol = Infinity;
  let sortCorrect = true;
  for (let i = 0; i < items.length; i++) {
    const vol = parseFloat(items[i].liquidity?.volume_24h || '0');
    if (vol > prevVol) {
      console.log(`SORT ERROR at position ${i}: ${vol} > ${prevVol}`);
      sortCorrect = false;
    }
    prevVol = vol;
  }

  console.log(`Sort is ${sortCorrect ? 'CORRECT' : 'INCORRECT'}`);
});

test('search for elon musk markets', async ({ page, request }) => {
  // Search for Elon Musk markets specifically
  const response = await request.get('http://localhost:8000/api/markets?search=elon&sort_by=volume_24h&sort_desc=true&page_size=20');
  const data = await response.json();

  console.log('\n=== ELON MUSK MARKETS ===\n');
  console.log(`Found ${data.total} markets matching "elon"`);

  const items = data.items || [];
  for (let i = 0; i < Math.min(10, items.length); i++) {
    const market = items[i];
    const vol24h = parseFloat(market.liquidity?.volume_24h || '0');

    console.log(`${i + 1}. Vol: $${vol24h.toLocaleString()} | ${market.question?.substring(0, 60)}...`);
  }

  // Also search for tweets
  const tweetsResponse = await request.get('http://localhost:8000/api/markets?search=tweet&sort_by=volume_24h&sort_desc=true&page_size=20');
  const tweetsData = await tweetsResponse.json();

  console.log('\n=== TWEET MARKETS ===\n');
  console.log(`Found ${tweetsData.total} markets matching "tweet"`);

  const tweetItems = tweetsData.items || [];
  for (let i = 0; i < Math.min(10, tweetItems.length); i++) {
    const market = tweetItems[i];
    const vol24h = parseFloat(market.liquidity?.volume_24h || '0');

    console.log(`${i + 1}. Vol: $${vol24h.toLocaleString()} | ${market.question?.substring(0, 60)}...`);
  }
});
