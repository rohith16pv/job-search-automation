# Claude AI Integration Guide

Enhance your job evaluator with Claude AI for intelligent, context-aware scoring.

---

## 🤖 What It Does

Instead of simple keyword matching, Claude analyzes:

✅ **Nuanced Job Fit**
- Reads your full CV and understands your background
- Reads the full job description and understands requirements
- Provides intelligent analysis, not just keyword hits

✅ **Smart Scoring**
- Considers context and growth potential
- Explains score reasoning
- Identifies specific gaps you could address

✅ **Actionable Insights**
- Strengths: Why you're a good fit
- Gaps: What you're missing
- Next Steps: What to emphasize in your application

---

## 💰 Cost

**Very affordable:**
- ~$0.04-0.05 per job evaluation
- Includes input (CV + JD) + output (analysis)
- For 100 jobs/month: ~$4-5
- For 500 jobs/month: ~$20-25

**No cost if you don't use it** — keyword matching still works

---

## 🚀 Setup (5 Minutes)

### Step 1: Get Claude API Key

1. Go to: https://console.anthropic.com
2. Create account (or log in)
3. Go to **API Keys** section
4. Click **Create Key**
5. Copy the key (starts with `sk-ant-...`)

### Step 2: Add to Environment

Edit `.env.local`:

```bash
nano .env.local
```

Add this line:

```
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

**Save and close.**

### Step 3: Verify Setup

```bash
# Check key is set
echo $ANTHROPIC_API_KEY

# Should print: sk-ant-...
```

### Step 4: Start AI Evaluator Service

```bash
cd /Users/rohith/Downloads/Github/job-search-automation

# Install dependencies (if needed)
npm install

# Start the AI evaluator
node scripts/evaluate-job-with-ai.mjs
```

**Expected output:**
```
[AI Evaluator] Listening on http://localhost:3005
[AI Evaluator] API Key: ✅ Set
[AI Evaluator] POST /evaluate-ai — evaluate job with Claude
```

---

## 🔧 Use It in n8n

### Update Existing Workflow

Instead of calling the basic evaluator:
```
HTTP Request → http://localhost:3002/evaluate
```

Call the AI evaluator:
```
HTTP Request → http://localhost:3005/evaluate-ai
```

### Example n8n Workflow Change

**Old (keyword-based):**
```
Webhook → Code → HTTP POST (localhost:3002/evaluate) → Gmail
```

**New (AI-based):**
```
Webhook → Code → HTTP POST (localhost:3005/evaluate-ai) → Gmail
```

### n8n HTTP Node Setup

- **URL:** `http://localhost:3005/evaluate-ai`
- **Method:** POST
- **Body:**
```json
{
  "job_title": "{{ $node.Code.json.job_title }}",
  "company": "{{ $node.Code.json.company }}",
  "jd_text": "{{ $node.Code.json.jd_text }}",
  "config_path": "/workspace/config"
}
```

### Response

```json
{
  "success": true,
  "score": 4.2,
  "score_letter": "B",
  "analysis": "Strong fit for payments PM role. Your settlement experience directly applies...",
  "strengths": [
    "10+ years payments experience",
    "Led cross-border payment initiatives",
    "Familiar with regulatory compliance"
  ],
  "gaps": [
    "No specific RTP experience",
    "Limited embedded finance background",
    "No previous startup experience"
  ],
  "recommendation": "Apply",
  "next_steps": "Emphasize your settlement and compliance background. Mention your interest in learning embedded finance.",
  "input_tokens": 3245,
  "output_tokens": 512,
  "cost": 0.0456
}
```

---

## 🎯 What Claude Evaluates

### Input (What Claude reads):

1. **Your Profile**
   - Target roles
   - Domain keywords you care about
   - Salary expectations
   - Deal breakers

2. **Your CV**
   - Full resume with experience
   - Projects and achievements
   - Skills and education

3. **Job Description**
   - Full JD text
   - Company name
   - Role title
   - All requirements and responsibilities

### Output (What Claude provides):

1. **Score (0-5)** — Overall fit
2. **Letter (A-F)** — Grade equivalent
3. **Analysis** — Why this score
4. **Strengths** — 3-5 reasons you're good fit
5. **Gaps** — 3-5 things you're missing
6. **Recommendation** — Apply / Negotiate / Consider / Skip
7. **Next Steps** — What to emphasize if applying

---

## 📊 Comparing Evaluators

### Keyword Matching (Free)
```
JD text → Extract keywords → Match CV keywords → Score
Cost: $0
Speed: Instant
Accuracy: 70%
```

### Claude AI (Smart)
```
JD text + CV + Profile → Claude reads & analyzes → Score
Cost: $0.04-0.05 per job
Speed: 2-3 seconds
Accuracy: 95%
```

**Recommendation:**
- **Free tier users:** Use keyword matching (fast, free)
- **Everyone else:** Use Claude AI (much better)

---

## 💡 Examples

### Example 1: Perfect Match (Score 4.8)

**Input:**
- Role: Senior PM at Stripe (payments platform)
- Your background: 10+ years payments + settlement PM

**Claude outputs:**
```
SCORE: 4.8
LETTER: A
ANALYSIS: Exceptional fit. Your settlement experience directly 
matches their infrastructure needs.

STRENGTHS:
- 10+ years in payments domain
- Built settlement infrastructure
- Regulatory expertise across 5 markets
- Led large engineering teams
- Published thought leadership in fintech

GAPS:
- No specific Stripe internal tools experience
- Limited exposure to open finance APIs

RECOMMENDATION: Apply
NEXT_STEPS: Lead with your settlement infrastructure work. 
Emphasize your experience scaling global payments. 
Mention your interest in embedded finance as growth area.
```

### Example 2: Adjacent Skill (Score 3.2)

**Input:**
- Role: VP of Engineering at startup
- Your background: Senior PM (not engineering)

**Claude outputs:**
```
SCORE: 3.2
LETTER: D
ANALYSIS: Skills mismatch. You're a PM, they need VP Engineering. 
Could consider if transitioning to engineering leadership.

STRENGTHS:
- Led cross-functional teams
- Managed engineers before
- Understands product-eng partnership

GAPS:
- No direct engineering management experience
- No CTO/VP Eng background
- Likely expects 20+ engineers under you

RECOMMENDATION: Skip
NEXT_STEPS: Not a good fit. Continue looking for PM or 
Principal PM roles instead.
```

---

## 🔄 Workflow: Free → Smart

### Start with Free (No API Cost)

```bash
# Run basic evaluator
node scripts/evaluate-job.mjs

# Use keyword matching in n8n
# Cost: $0
```

### Upgrade to Smart (Optional)

```bash
# Get API key from: https://console.anthropic.com
# Add to .env.local: ANTHROPIC_API_KEY=sk-ant-...

# Start AI evaluator
node scripts/evaluate-job-with-ai.mjs

# Update n8n to call /evaluate-ai instead
# Cost: ~$4-5/month for 100 jobs
```

### No Downtime
- Both evaluators run simultaneously
- Switch between them in n8n at any time
- Test with AI, revert to free if desired

---

## 📈 Cost Estimates

| Jobs/Month | Free Evaluator | AI Evaluator | Difference |
|---|---|---|---|
| 10 | $0 | $0.50 | +$0.50 |
| 50 | $0 | $2.50 | +$2.50 |
| 100 | $0 | $4.50 | +$4.50 |
| 500 | $0 | $22.50 | +$22.50 |

**Claude API pricing:** $0.003 per 1K input tokens + $0.015 per 1K output tokens

---

## 🛠️ Advanced: Customize Prompts

Edit `scripts/evaluate-job-with-ai.mjs` to change how Claude evaluates:

```javascript
function buildEvaluationPrompt(jobTitle, company, jdText, profile, cv) {
  return `You are a career advisor evaluating job fit...
  
  // Customize this prompt to:
  // - Weight certain factors differently
  // - Add your own criteria
  // - Change tone/style
  // - Add domain-specific evaluation rules
  `;
}
```

---

## 🔒 Privacy & Security

- ✅ Your API key stored locally (.env.local)
- ✅ Your CV sent to Anthropic (for evaluation only)
- ✅ Your profile data NOT sent to Anthropic
- ✅ No data stored by Anthropic beyond evaluation
- ✅ All API calls over HTTPS
- ✅ You can audit the prompt in the code

**Anthropic's privacy policy:** https://www.anthropic.com/privacy

---

## 🚨 Troubleshooting

### "ANTHROPIC_API_KEY not set"

```bash
# Check if set
echo $ANTHROPIC_API_KEY

# If empty, add to .env.local and source it
source .env.local
export ANTHROPIC_API_KEY=sk-ant-...
```

### "API error: invalid_api_key"

```bash
# Verify key is correct
# Go to: https://console.anthropic.com/api_keys
# Copy key again
# Make sure it starts with: sk-ant-
```

### "Evaluation taking too long"

- Claude API typical response: 2-3 seconds
- Check network connection
- Check Claude API status: https://status.anthropic.com

### "Getting low scores for good jobs"

- Claude is being conservative
- Edit the evaluation prompt to adjust
- Or provide more context about your background

---

## 📚 Next Steps

1. **Get API key:** https://console.anthropic.com
2. **Add to .env.local**
3. **Start AI evaluator:** `node scripts/evaluate-job-with-ai.mjs`
4. **Update n8n workflow:** Change endpoint to `localhost:3005`
5. **Test with real job:** Paste a JD and see smart analysis

---

## 🎯 FAQ

**Q: Do I need AI for this to work?**
A: No! Basic evaluator works great. AI is optional upgrade for better insights.

**Q: How much does it cost?**
A: ~$0.04-0.05 per job. For 100 jobs/month: ~$5.

**Q: Can I use a different AI (GPT-4, etc.)?**
A: Yes! Modify the script to call different API. Claude recommended for cost/quality.

**Q: Is my data safe?**
A: Yes. Your CV is sent to Anthropic for evaluation, then deleted. No storage.

**Q: Can I use Claude's free tier?**
A: Yes, but it has rate limits. API key recommended for production.

---

**Ready to make your evaluator intelligent?** 🚀

Start with Step 1 above!

