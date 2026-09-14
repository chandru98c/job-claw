import { execSync } from 'child_process';
import path from 'path';

async function globalSetup() {
    console.log("Seeding E2E Database...");
    execSync('python scripts/seed_e2e.py', {
        cwd: path.resolve(__dirname, '../../backend'),
        stdio: 'inherit',
        env: {
            ...process.env,
            DATABASE_URL: 'postgresql+asyncpg://postgres:Postpass123@localhost:5432/jobclaw_test',
        }
    });
}

export default globalSetup;
