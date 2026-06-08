#!/usr/bin/env node

/**
 * resume-tweaker.mjs
 *
 * Analyze CV against JD and suggest resume section reordering.
 * Does NOT modify cv.md. Returns suggestions only.
 *
 * Input:
 * {
 *   cv_path: "/workspace/career-ops/cv.md",
 *   jd_text: "Full JD content...",
 *   company: "Company Name",
 *   role: "Role Title"
 * }
 *
 * Output:
 * {
 *   original_order: ["Experience", "Projects", "Education"],
 *   suggested_order: ["Experience", "Projects", "Education"],
 *   reasoning: "...",
 *   matches: {
 *     Experience: ["bullet 1", "bullet 2"],
 *     Projects: ["project 1"]
 *   },
 *   confidence: 0.85,
 *   recommendation: "High confidence in reorder"
 * }
 */

import { readFileSync, existsSync } from 'fs';
import path from 'path';

function parseCV(cvText) {
  const sections = {};
  const sectionRegex = /^##\s+(\w+)\s*$/gm;
  const lines = cvText.split('\n');

  let currentSection = null;
  let currentContent = [];

  for (const line of lines) {
    const match = line.match(/^##\s+(\w+)/);
    if (match) {
      if (currentSection) {
        sections[currentSection] = currentContent.join('\n').trim();
      }
      currentSection = match[1];
      currentContent = [];
    } else if (currentSection) {
      currentContent.push(line);
    }
  }

  if (currentSection) {
    sections[currentSection] = currentContent.join('\n').trim();
  }

  return sections;
}

function extractBullets(sectionText) {
  // Find lines starting with -
  return sectionText
    .split('\n')
    .filter(line => line.trim().startsWith('-'))
    .map(line => line.trim());
}

function findKeywordMatches(cvSections, jdText) {
  const jdLower = jdText.toLowerCase();
  const matches = {};

  for (const [section, content] of Object.entries(cvSections)) {
    const bullets = extractBullets(content);
    const sectionMatches = [];

    for (const bullet of bullets) {
      const bulletLower = bullet.toLowerCase();
      // Simple scoring: count keyword overlap
      const words = bulletLower.split(/\s+/);
      const matches_count = words.filter(w => jdLower.includes(w)).length;

      if (matches_count >= 3) {
        // At least 3 word matches
        sectionMatches.push({
          bullet: bullet.substring(0, 100) + '...',
          matches: matches_count,
        });
      }
    }

    if (sectionMatches.length > 0) {
      matches[section] = sectionMatches;
    }
  }

  return matches;
}

function suggestReordering(matches, originalOrder) {
  // Score each section by total matches
  const sectionScores = {};

  for (const section of originalOrder) {
    sectionScores[section] = matches[section]
      ? matches[section].reduce((sum, m) => sum + m.matches, 0)
      : 0;
  }

  // Sort by score descending, keep unmatched at end
  const suggestedOrder = originalOrder.sort((a, b) => {
    const scoreA = sectionScores[a];
    const scoreB = sectionScores[b];

    if (scoreA === 0 && scoreB === 0) return 0;
    if (scoreA === 0) return 1;
    if (scoreB === 0) return -1;

    return scoreB - scoreA;
  });

  return { suggestedOrder, sectionScores };
}

function assessConfidence(matches, sectionScores) {
  const totalMatches = Object.values(matches).reduce(
    (sum, m) => sum + m.length,
    0
  );

  if (totalMatches === 0) return { confidence: 0, reason: 'No keyword matches found' };
  if (totalMatches >= 10) return { confidence: 0.9, reason: 'Strong match signal' };
  if (totalMatches >= 5) return { confidence: 0.7, reason: 'Moderate match signal' };
  return { confidence: 0.5, reason: 'Few matches, consider original order' };
}

async function tweakResume(input) {
  try {
    const { cv_path, jd_text, company, role } = input;

    console.log(`[resume-tweaker] Analyzing ${company} — ${role}`);

    // Read CV
    if (!existsSync(cv_path)) {
      throw new Error(`CV not found: ${cv_path}`);
    }

    const cvText = readFileSync(cv_path, 'utf-8');
    const cvSections = parseCV(cvText);
    const originalOrder = Object.keys(cvSections);

    console.log(`[resume-tweaker] CV sections: ${originalOrder.join(', ')}`);

    // Analyze
    const matches = findKeywordMatches(cvSections, jdText);
    const { suggestedOrder, sectionScores } = suggestReordering(matches, originalOrder);
    const { confidence, reason } = assessConfidence(matches, sectionScores);

    // Build recommendation
    let recommendation = 'Consider original order';
    if (confidence >= 0.7) {
      recommendation = `RECOMMENDED: Reorder to [${suggestedOrder.join(' → ')}]`;
    } else if (confidence >= 0.5) {
      recommendation = `OPTIONAL: Suggested reorder to [${suggestedOrder.join(' → ')}] but original is fine`;
    }

    return {
      success: true,
      original_order: originalOrder,
      suggested_order: suggestedOrder,
      confidence: Number(confidence.toFixed(2)),
      confidence_reason: reason,
      matches: Object.fromEntries(
        Object.entries(matches).map(([section, sectionMatches]) => [
          section,
          sectionMatches.map(m => m.bullet),
        ])
      ),
      section_scores: sectionScores,
      recommendation,
      note: 'User must approve reordering before PDF generation',
    };
  } catch (error) {
    console.error('[resume-tweaker] Error:', error.message);
    return {
      success: false,
      error: error.message,
      recommendation: 'Use original CV section order',
    };
  }
}

// HTTP server
import express from 'express';

const app = express();
const PORT = process.env.PORT || 3004;

app.use(express.json());

app.post('/suggest', async (req, res) => {
  const result = await tweakResume(req.body);
  res.json(result);
});

app.get('/health', (req, res) => {
  res.json({ status: 'ok', service: 'resume-tweaker' });
});

app.listen(PORT, () => {
  console.log(`[resume-tweaker] Listening on http://localhost:${PORT}`);
  console.log(`[resume-tweaker] POST /suggest — suggest resume tweaks`);
});
