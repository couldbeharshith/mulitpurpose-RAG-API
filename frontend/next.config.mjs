import { PHASE_DEVELOPMENT_SERVER } from 'next/constants.js';

/** @returns {import('next').NextConfig} */
export default function config(phase) {
  const shared = { trailingSlash: true, devIndicators: false, agentRules: false };

  if (phase === PHASE_DEVELOPMENT_SERVER) {
    return {
      ...shared,
      async redirects() {
        return [{ source: '/workspace/', destination: '/', permanent: false }];
      },
    };
  }

  return { ...shared, basePath: '/workspace', output: 'export' };
}
