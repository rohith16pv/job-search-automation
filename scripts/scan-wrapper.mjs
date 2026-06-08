#!/usr/bin/env node

/**
 * scan-wrapper.mjs
 *
 * Scans configured ATS portals for new job postings.
 * Called via webhook from n8n, returns JSON array of new jobs.
 *
 * Fully standalone — no career-ops dependency.
 */

import YAML from 'yaml';
import { readFileSync, writeFileSync, existsSync } from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const CONFIG_PATH = path.join(__dirname, '../config/portals.yml');
const DATA_PATH = path.join(__dirname, '../data');

async function scanJobs() {
  try {
    console.log('[scan-wrapper] Starting job scan...');

    // Load config
    if (!existsSync(CONFIG_PATH)) {
      throw new Error(`portals.yml not found at ${CONFIG_PATH}`);
    }

    const config = YAML.parse(readFileSync(CONFIG_PATH, 'utf-8'));
    const portals = config.portals || [];

    console.log(`[scan-wrapper] Configured portals: ${portals.length}`);

    // Mock job results (in production, would hit real APIs)
    const jobs = generateMockJobs(portals, config);

    console.log(`[scan-wrapper] Found ${jobs.length} jobs from portals`);

    // Load scan history to detect new jobs
    const history = loadScanHistory();
    const newJobs = jobs.filter(job => !history.includes(job.id));

    console.log(`[scan-wrapper] New jobs: ${newJobs.length}`);

    // Save to scan history
    newJobs.forEach(job => {
      history.push(job.id);
    });
    saveScanHistory(history);

    return {
      success: true,
      jobs: newJobs,
      total_found: jobs.length,
      new_count: newJobs.length,
      timestamp: new Date().toISOString(),
    };
  } catch (error) {
    console.error('[scan-wrapper] Error:', error.message);
    return {
      success: false,
      error: error.message,
      jobs: [],
      total_found: 0,
      new_count: 0,
      timestamp: new Date().toISOString(),
    };
  }
}

function generateMockJobs(portals, config) {
  // Mock data for demo (replace with real API calls in production)
  const sampleJobs = [
    {
      id: 'stripe-pm-001',
      company: 'Stripe',
      role: 'Senior Product Manager - Payments',
      url: 'https://jobs.stripe.com/payments-pm',
      posted_date: new Date().toISOString().split('T')[0],
      source: 'stripe_careers',
      description: 'Lead payments product initiatives. Build settlement infrastructure.',
      compensation: '$300k-$350k base + equity',
    },
    {
      id: 'square-pm-002',
      company: 'Square',
      role: 'Staff Product Manager - Money Movement',
      url: 'https://jobs.square.com/money-pm',
      posted_date: new Date().toISOString().split('T')[0],
      source: 'square_careers',
      description: 'Own money movement platform. 100+ engineers on your team.',
      compensation: '$320k-$380k base + equity',
    },
    {
      id: 'adyen-pm-003',
      company: 'Adyen',
      role: 'Senior Product Manager - API Payments',
      url: 'https://jobs.adyen.com/api-pm',
      posted_date: new Date().toISOString().split('T')[0],
      source: 'adyen_careers',
      description: 'Build embedded finance API. Scale to 1000+ integrations.',
      compensation: '$280k-$330k base + equity',
    },
  ];

  return sampleJobs;
}

function loadScanHistory() {
  const historyPath = path.join(DATA_PATH, 'scan_history.jsonl');
  if (!existsSync(historyPath)) return [];

  return readFileSync(historyPath, 'utf-8')
    .split('\n')
    .filter(line => line.trim())
    .map(line => JSON.parse(line).id);
}

function saveScanHistory(ids) {
  const historyPath = path.join(DATA_PATH, 'scan_history.jsonl');
  const content = ids.map(id => JSON.stringify({ id, timestamp: new Date().toISOString() })).join('\n');
  writeFileSync(historyPath, content);
}

// HTTP server for n8n webhook
import express from 'express';

const app = express();
const PORT = process.env.PORT || 3001;

app.use(express.json());

app.post('/scan', async (req, res) => {
  const result = await scanJobs();
  res.json(result);
});

app.get('/health', (req, res) => {
  res.json({ status: 'ok', service: 'scan-wrapper' });
});

app.listen(PORT, () => {
  console.log(`[scan-wrapper] Listening on http://localhost:${PORT}`);
  console.log(`[scan-wrapper] POST /scan — scan jobs`);
  console.log(`[scan-wrapper] GET /health — health check`);
});
