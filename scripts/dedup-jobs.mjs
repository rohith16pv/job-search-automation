#!/usr/bin/env node

/**
 * dedup-jobs.mjs
 * Check if a job posting already exists in local scan history.
 * Fully standalone — no career-ops dependency.
 */

import { readFileSync, writeFileSync, existsSync } from 'fs';
import path from 'path';
import crypto from 'crypto';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const DATA_PATH = path.join(__dirname, '../data');

function loadScanHistory() {
  const historyPath = path.join(DATA_PATH, 'scan_history.jsonl');

  if (!existsSync(historyPath)) {
    console.log('[dedup] scan_history.jsonl not found, starting fresh');
    return [];
  }

  const content = readFileSync(historyPath, 'utf-8');
  return content
    .split('\n')
    .filter(line => line.trim())
    .map(line => {
      try {
        return JSON.parse(line);
      } catch {
        return null;
      }
    })
    .filter(Boolean);
}

function generateContentHash(jdText) {
  // Normalize JD: lowercase, remove extra whitespace
  const normalized = jdText.toLowerCase().replace(/\s+/g, ' ').trim();
  return crypto.createHash('sha256').update(normalized).digest('hex');
}

function checkDuplicate(input) {
  try {
    const {
      company,
      role,
      posting_url,
      jd_text, // Optional: for content-based dedup
    } = input;

    const history = loadScanHistory();

    // URL-based dedup (primary)
    const urlMatch = history.find(h => h.url === posting_url);
    if (urlMatch) {
      return {
        is_duplicate: true,
        reason: 'URL match',
        last_seen: urlMatch.date,
        days_since: daysAgo(urlMatch.date),
      };
    }

    // Company + role dedup (secondary, for reposts with different URLs)
    const contentMatch = history.find(
      h => h.company === company && h.role === role
    );

    if (contentMatch && jd_text) {
      // Content-based check
      const existingHash = contentMatch.hash;
      const newHash = generateContentHash(jd_text);

      if (existingHash === newHash || similarity(existingHash, newHash) > 0.8) {
        return {
          is_duplicate: true,
          reason: 'Content match (likely repost)',
          last_seen: contentMatch.date,
          days_since: daysAgo(contentMatch.date),
        };
      }
    }

    // Not a duplicate
    return {
      is_duplicate: false,
      reason: 'New job posting',
      last_seen: null,
      days_since: null,
    };
  } catch (error) {
    console.error('[dedup] Error:', error.message);
    return {
      is_duplicate: false,
      error: error.message,
    };
  }
}

function daysAgo(dateStr) {
  const posted = new Date(dateStr);
  const now = new Date();
  const diff = now - posted;
  return Math.floor(diff / (1000 * 60 * 60 * 24));
}

function similarity(a, b) {
  // Very basic string similarity (Hamming distance normalized)
  if (!a || !b) return 0;
  const minLen = Math.min(a.length, b.length);
  let matches = 0;
  for (let i = 0; i < minLen; i++) {
    if (a[i] === b[i]) matches++;
  }
  return matches / Math.max(a.length, b.length);
}

// HTTP server
import express from 'express';

const app = express();
const PORT = process.env.PORT || 3003;

app.use(express.json());

app.post('/check', (req, res) => {
  const result = checkDuplicate(req.body);
  res.json(result);
});

app.get('/health', (req, res) => {
  res.json({ status: 'ok', service: 'dedup-jobs' });
});

app.listen(PORT, () => {
  console.log(`[dedup] Listening on http://localhost:${PORT}`);
  console.log(`[dedup] POST /check — check if job is duplicate`);
});
