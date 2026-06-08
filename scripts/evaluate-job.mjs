#!/usr/bin/env node

/**
 * evaluate-job.mjs
 *
 * Standalone job evaluator for n8n integration.
 * Keyword matching + basic scoring. No external dependencies.
 *
 * Input (from n8n):
 * {
 *   job_title: "Senior Product Manager",
 *   company: "Company Name",
 *   jd_text: "Full JD content...",
 *   config_path: "/workspace/config"
 * }
 *
 * Output:
 * {
 *   score: 4.2,
 *   score_letter: "B",
 *   gaps: [...],
 *   comp_estimate: "$250k-300k",
 *   legitimacy_tier: "High",
 *   keywords_matched: [...],
 *   suggested_sections: [...]
 * }
 */

import { readFileSync, existsSync } from 'fs';
import path from 'path';
import YAML from 'yaml';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Load profile from local config
function loadProfile(configPath = null) {
  const profilePath = configPath ? path.join(configPath, 'profile.yml') : path.join(__dirname, '../config/profile.yml');

  if (!existsSync(profilePath)) {
    console.warn(`[evaluate] profile.yml not found at ${profilePath}, using defaults`);
    return {
      target_roles: ['Senior PM', 'Staff PM', 'Product Manager', 'Director of Product'],
      domain_keywords: [
        'payments', 'fintech', 'settlement', 'ACH', 'RTP',
        'embedded finance', 'BaaS', 'cross-border', 'FX', 'rails',
        'treasury', 'money movement', 'liquidity'
      ],
      nice_to_have: [
        'API', 'infrastructure', 'scalability', 'B2B', 'SaaS',
        'mobile', 'web', 'compliance', 'risk'
      ],
    };
  }

  const config = YAML.parse(readFileSync(profilePath, 'utf-8'));
  return {
    target_roles: config.targeting?.target_roles || [],
    domain_keywords: config.targeting?.domain_keywords || [],
    nice_to_have: config.targeting?.nice_to_have_keywords || [],
  };
}

function extractKeywords(text) {
  const lower = text.toLowerCase();
  const matched = {
    domain: [],
    nice_to_have: [],
  };

  PROFILE.domain_keywords.forEach(kw => {
    if (lower.includes(kw.toLowerCase())) {
      matched.domain.push(kw);
    }
  });

  PROFILE.nice_to_have.forEach(kw => {
    if (lower.includes(kw.toLowerCase())) {
      matched.nice_to_have.push(kw);
    }
  });

  return matched;
}

function assessTitleMatch(jobTitle) {
  const lower = jobTitle.toLowerCase();

  // Hard blocks
  const blockers = ['VP', 'Head of', 'Associate', 'Junior', 'Intern', 'APM', 'Engineering'];
  if (blockers.some(b => lower.includes(b.toLowerCase()))) {
    return { score: 0, reason: 'Title blocked (level mismatch)' };
  }

  // Positive signals
  const senior_signals = ['Senior', 'Staff', 'Principal', 'Director', 'Founding'];
  if (senior_signals.some(s => lower.includes(s.toLowerCase()))) {
    return { score: 2, reason: 'Target seniority level detected' };
  }

  // Neutral (generic PM)
  if (lower.includes('product manager') || lower.includes('pm')) {
    return { score: 1, reason: 'Generic PM title (check seniority in JD)' };
  }

  return { score: 0, reason: 'Title does not match target roles' };
}

function calculateScore(titleScore, keywords, jdLength) {
  let score = titleScore / 2; // 0-1

  // Domain keyword match: max 1.5 points
  const domainScore = Math.min(keywords.domain.length * 0.3, 1.5);
  score += domainScore;

  // Nice to have: max 0.5 points
  const niceScore = Math.min(keywords.nice_to_have.length * 0.1, 0.5);
  score += niceScore;

  // JD length signal (too short = sketchy job posting)
  if (jdLength < 200) {
    score -= 0.5;
  } else if (jdLength > 2000) {
    score += 0.2;
  }

  return Math.min(Math.max(score * 1.25, 0), 5);
}

function getCompEstimate(jd) {
  // Very basic regex for salary
  const salaryMatch = jd.match(/\$(\d+)k?\s*[-–]\s*\$?(\d+)k?/i);
  if (salaryMatch) {
    return `$${salaryMatch[1]}k-${salaryMatch[2]}k`;
  }
  return 'Market rate';
}

function identifyGaps(keywords) {
  const gaps = [];

  if (keywords.domain.length === 0) {
    gaps.push('No payment/fintech domain keywords found in JD');
  }

  if (!keywords.domain.some(k => k.includes('payment') || k.includes('fintech'))) {
    gaps.push('Limited fintech-specific background signal');
  }

  return gaps;
}

function letterGrade(score) {
  if (score >= 4.5) return 'A';
  if (score >= 4.0) return 'B';
  if (score >= 3.5) return 'C';
  if (score >= 3.0) return 'D';
  return 'F';
}

async function evaluateJob(input) {
  try {
    const {
      job_title,
      company,
      jd_text,
      config_path, // Path to config directory
    } = input;

    console.log(`[evaluate-job] Evaluating ${company} — ${job_title}`);

    // Load profile from local config
    const PROFILE = loadProfile(config_path);

    // Assess title match
    const titleMatch = assessTitleMatch(job_title);

    // Extract keywords from JD
    const keywords = extractKeywords(jd_text);

    // Calculate score
    const score = calculateScore(
      titleMatch.score,
      keywords,
      jd_text.length
    );
    const letter = letterGrade(score);
    const comp = getCompEstimate(jd_text);
    const gaps = identifyGaps(keywords);

    // Suggested resume sections (where CV matches best)
    const suggested_sections = [];
    if (keywords.domain.length > 0) suggested_sections.push('Experience');
    if (keywords.nice_to_have.length > 0) suggested_sections.push('Projects');
    if (score > 3.5) suggested_sections.push('Skills');

    const result = {
      score: Number(score.toFixed(1)),
      score_letter: letter,
      title_match: titleMatch.reason,
      gaps: gaps.length > 0 ? gaps : ['None identified'],
      comp_estimate: comp,
      legitimacy_tier: jd_text.length > 500 ? 'High' : 'Medium',
      keywords_matched: [...new Set([...keywords.domain, ...keywords.nice_to_have])],
      suggested_sections: [...new Set(suggested_sections)],
      assessment: `${letter} fit: ${titleMatch.reason}. Domain match: ${keywords.domain.length} signals found.`,
    };

    console.log(`[evaluate-job] Result: ${letter}/${score} fit`);
    return result;
  } catch (error) {
    console.error('[evaluate-job] Error:', error.message);
    throw error;
  }
}

// HTTP server for n8n webhook
import express from 'express';

const app = express();
const PORT = process.env.PORT || 3002;

app.use(express.json());

app.post('/evaluate', async (req, res) => {
  try {
    const result = await evaluateJob(req.body);
    res.json({ success: true, ...result });
  } catch (error) {
    res.status(400).json({ success: false, error: error.message });
  }
});

app.get('/health', (req, res) => {
  res.json({ status: 'ok', service: 'evaluate-job' });
});

app.listen(PORT, () => {
  console.log(`[evaluate-job] Listening on http://localhost:${PORT}`);
  console.log(`[evaluate-job] POST /evaluate — evaluate job`);
});
