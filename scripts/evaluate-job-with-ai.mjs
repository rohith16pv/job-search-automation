#!/usr/bin/env node

/**
 * evaluate-job-with-ai.mjs
 *
 * Smart job evaluator using Claude API.
 * Reads CV + profile from local config.
 * Calls Claude to intelligently score job fit.
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
 *   analysis: "Strong fit because...",
 *   gaps: ["No X experience"],
 *   strengths: ["Matches Y"],
 *   next_steps: "Apply and mention Z",
 *   cost: 0.045
 * }
 */

import { readFileSync, existsSync } from 'fs';
import path from 'path';
import YAML from 'yaml';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const ANTHROPIC_API_KEY = process.env.ANTHROPIC_API_KEY;
const ANTHROPIC_API_URL = 'https://api.anthropic.com/v1/messages';

// Costs (as of 2024)
const COSTS = {
  input_per_1k: 0.003,    // $0.003 per 1K input tokens
  output_per_1k: 0.015,   // $0.015 per 1K output tokens
};

function loadProfile(configPath = null) {
  const profilePath = configPath ? path.join(configPath, 'profile.yml') : path.join(__dirname, '../config/profile.yml');

  if (!existsSync(profilePath)) {
    console.warn(`[AI Evaluator] profile.yml not found, using defaults`);
    return {
      target_roles: ['Senior PM', 'Staff PM'],
      domain_keywords: ['payments', 'fintech'],
      blockers: [],
      compensation: { target_base_min: 250000 }
    };
  }

  const config = YAML.parse(readFileSync(profilePath, 'utf-8'));
  return {
    full_name: config.candidate?.full_name || 'Candidate',
    email: config.candidate?.email || 'unknown@example.com',
    target_roles: config.targeting?.target_roles || [],
    domain_keywords: config.targeting?.domain_keywords || [],
    blockers: config.targeting?.blockers || [],
    nice_to_have: config.targeting?.nice_to_have_keywords || [],
    compensation: config.compensation || {},
  };
}

function loadCV(configPath = null) {
  const cvPath = configPath ? path.join(configPath, 'cv.md') : path.join(__dirname, '../config/cv.md');

  if (!existsSync(cvPath)) {
    console.warn(`[AI Evaluator] CV not found`);
    return 'No CV available';
  }

  return readFileSync(cvPath, 'utf-8');
}

async function evaluateWithClaude(input) {
  if (!ANTHROPIC_API_KEY) {
    throw new Error('ANTHROPIC_API_KEY environment variable not set');
  }

  const { job_title, company, jd_text, config_path } = input;

  console.log(`[AI Evaluator] Evaluating ${company} — ${job_title}`);

  // Load profile + CV
  const profile = loadProfile(config_path);
  const cv = loadCV(config_path);

  // Build prompt
  const prompt = buildEvaluationPrompt(job_title, company, jd_text, profile, cv);

  console.log(`[AI Evaluator] Calling Claude API...`);

  // Call Claude API
  const response = await fetch(ANTHROPIC_API_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'x-api-key': ANTHROPIC_API_KEY,
      'anthropic-version': '2023-06-01',
    },
    body: JSON.stringify({
      model: 'claude-3-5-sonnet-20241022',
      max_tokens: 1024,
      messages: [
        {
          role: 'user',
          content: prompt,
        },
      ],
    }),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(`Claude API error: ${error.error?.message || JSON.stringify(error)}`);
  }

  const result = await response.json();
  const content = result.content[0].text;

  // Parse response
  const evaluation = parseClaudeResponse(content);

  // Calculate cost
  const inputTokens = result.usage.input_tokens;
  const outputTokens = result.usage.output_tokens;
  const cost = (inputTokens / 1000) * COSTS.input_per_1k + (outputTokens / 1000) * COSTS.output_per_1k;

  console.log(`[AI Evaluator] Evaluation complete. Cost: $${cost.toFixed(4)}`);

  return {
    ...evaluation,
    input_tokens: inputTokens,
    output_tokens: outputTokens,
    cost: Number(cost.toFixed(4)),
  };
}

function buildEvaluationPrompt(jobTitle, company, jdText, profile, cv) {
  return `You are a career advisor evaluating job fit for a candidate.

CANDIDATE PROFILE:
- Name: ${profile.full_name}
- Target Roles: ${profile.target_roles.join(', ')}
- Domain Interest: ${profile.domain_keywords.join(', ')}
- Salary Target: $${profile.compensation.target_base_min}k+
- Deal Breakers: ${profile.blockers.join(', ') || 'None'}

CANDIDATE'S CV:
\`\`\`
${cv}
\`\`\`

JOB OPENING:
- Company: ${company}
- Role: ${jobTitle}
- Job Description:
\`\`\`
${jdText}
\`\`\`

EVALUATE THIS JOB:

1. SCORE (0-5): Rate overall fit
2. LETTER (A-F): Grade equivalent (A=4.5-5.0, B=4.0-4.4, C=3.5-3.9, D=3.0-3.4, F=<3.0)
3. ANALYSIS: 1-2 sentences on why this score
4. STRENGTHS (bullet list): 3-5 reasons they're a good fit
5. GAPS (bullet list): 3-5 skills/experience missing
6. RECOMMENDATION: "Apply", "Negotiate", "Consider", or "Skip"
7. NEXT STEPS: If applying, what to emphasize in cover letter

Format your response EXACTLY as:

SCORE: X.X
LETTER: X
ANALYSIS: [Your analysis]
STRENGTHS:
- [Strength 1]
- [Strength 2]
GAPS:
- [Gap 1]
- [Gap 2]
RECOMMENDATION: [Apply/Negotiate/Consider/Skip]
NEXT_STEPS: [What to emphasize]

Be concise, specific, and honest. If score is below 3.0, explain why firmly.`;
}

function parseClaudeResponse(text) {
  const lines = text.split('\n');
  const result = {
    score: 0,
    score_letter: 'F',
    analysis: '',
    strengths: [],
    gaps: [],
    recommendation: 'Skip',
    next_steps: '',
  };

  let currentSection = null;

  for (const line of lines) {
    const trimmed = line.trim();

    if (trimmed.startsWith('SCORE:')) {
      const scoreStr = trimmed.replace('SCORE:', '').trim();
      result.score = parseFloat(scoreStr);
    } else if (trimmed.startsWith('LETTER:')) {
      result.score_letter = trimmed.replace('LETTER:', '').trim();
    } else if (trimmed.startsWith('ANALYSIS:')) {
      result.analysis = trimmed.replace('ANALYSIS:', '').trim();
    } else if (trimmed.startsWith('STRENGTHS:')) {
      currentSection = 'strengths';
    } else if (trimmed.startsWith('GAPS:')) {
      currentSection = 'gaps';
    } else if (trimmed.startsWith('RECOMMENDATION:')) {
      result.recommendation = trimmed.replace('RECOMMENDATION:', '').trim();
    } else if (trimmed.startsWith('NEXT_STEPS:')) {
      result.next_steps = trimmed.replace('NEXT_STEPS:', '').trim();
    } else if (trimmed.startsWith('-') && currentSection) {
      const item = trimmed.substring(1).trim();
      if (currentSection === 'strengths') {
        result.strengths.push(item);
      } else if (currentSection === 'gaps') {
        result.gaps.push(item);
      }
    }
  }

  return result;
}

// HTTP server
import express from 'express';

const app = express();
const PORT = process.env.PORT || 3005;

app.use(express.json());

app.post('/evaluate-ai', async (req, res) => {
  try {
    const result = await evaluateWithClaude(req.body);
    res.json({ success: true, ...result });
  } catch (error) {
    console.error('[AI Evaluator] Error:', error.message);
    res.status(400).json({ success: false, error: error.message });
  }
});

app.get('/health', (req, res) => {
  res.json({ status: 'ok', service: 'evaluate-job-with-ai', api_key_set: !!ANTHROPIC_API_KEY });
});

app.listen(PORT, () => {
  console.log(`[AI Evaluator] Listening on http://localhost:${PORT}`);
  console.log(`[AI Evaluator] API Key: ${ANTHROPIC_API_KEY ? '✅ Set' : '❌ NOT SET'}`);
  console.log(`[AI Evaluator] POST /evaluate-ai — evaluate job with Claude`);
});
