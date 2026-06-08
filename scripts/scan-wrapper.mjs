#!/usr/bin/env node

/**
 * scan-wrapper.mjs
 *
 * Wrapper around career-ops scan.mjs for n8n integration.
 * Called via webhook from n8n, returns JSON array of new jobs.
 */

import { execSync } from 'child_process';
import path from 'path';
import { readFileSync } from 'fs';
import YAML from 'yaml';

const CAREER_OPS_PATH = process.env.CAREER_OPS_PATH || '/workspace/career-ops';

async function scanJobs() {
  try {
    // Run career-ops scan.mjs
    console.log('[scan-wrapper] Starting scan...');
    const scanOutput = execSync(`node ${CAREER_OPS_PATH}/scan.mjs --json`, {
      encoding: 'utf-8',
      cwd: CAREER_OPS_PATH,
    });

    // Parse output
    const jobs = JSON.parse(scanOutput);

    console.log(`[scan-wrapper] Found ${jobs.length} jobs`);

    // Enrich with metadata
    const enriched = jobs.map((job, idx) => ({
      id: `${job.company.toLowerCase().replace(/\s+/g, '-')}-${idx}`,
      company: job.company,
      role: job.title,
      url: job.url,
      posted_date: job.posted_date || new Date().toISOString().split('T')[0],
      source: job.source || 'unknown',
      description_preview: (job.description || '').slice(0, 200),
    }));

    return {
      success: true,
      jobs: enriched,
      count: enriched.length,
      timestamp: new Date().toISOString(),
    };
  } catch (error) {
    console.error('[scan-wrapper] Error:', error.message);
    return {
      success: false,
      error: error.message,
      jobs: [],
      count: 0,
      timestamp: new Date().toISOString(),
    };
  }
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
