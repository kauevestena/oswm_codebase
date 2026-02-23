// Script for actions/github-script@v7
// Creates a GitHub Issue when the daily pipeline fails.
// Step outcomes are passed in via env vars (DAILY_JOB_OUTCOME, VALIDATE_TILES_OUTCOME)
// to avoid GitHub Actions expression injection inside the script file.

const fs = require('fs');
const date = new Date().toISOString().split('T')[0];
const runUrl = `${process.env.GITHUB_SERVER_URL}/${process.env.GITHUB_REPOSITORY}/actions/runs/${process.env.GITHUB_RUN_ID}`;

const dailyJobOutcome      = process.env.DAILY_JOB_OUTCOME;
const validateTilesOutcome = process.env.VALIDATE_TILES_OUTCOME;

let body = `# Daily Pipeline Failure Report\n\n**Date:** ${date}\n**Run:** ${runUrl}\n\n`;

if (dailyJobOutcome === 'failure') {
  body += `## Pipeline Step Failures\n`;
  try {
    const failures = fs.readFileSync('data/pipeline_failures.txt', 'utf8').trim();
    body += failures + '\n\n';
  } catch (e) {
    body += `daily.sh exited with errors (no detail file found)\n\n`;
  }
}

if (validateTilesOutcome === 'failure') {
  body += `## Tile Validation Failures\n`;
  try {
    const report = fs.readFileSync('data/tiles/tile_generation_report.json', 'utf8');
    body += `\`\`\`json\n${report}\n\`\`\`\n`;
  } catch (e) {
    body += `Tile validation failed (no report file found)\n`;
  }
}

body += `\n---\n_This issue was automatically created by the daily pipeline._`;

// Ensure the label exists (create it if not)
try {
  await github.rest.issues.createLabel({
    owner: context.repo.owner,
    repo: context.repo.repo,
    name: 'pipeline-failure',
    color: 'e11d48',
    description: 'Automatically created when the daily pipeline fails'
  });
} catch (e) {
  // Label already exists — ignore 422 Unprocessable Entity
}

await github.rest.issues.create({
  owner: context.repo.owner,
  repo: context.repo.repo,
  title: `⚠ Daily pipeline failure — ${date}`,
  body,
  labels: ['pipeline-failure']
});
