import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  dqgSidebar: [
    {
      type: 'category',
      label: 'Genel Bakis',
      items: ['overview', 'quick-start'],
    },
    {
      type: 'category',
      label: 'Mimari',
      items: ['architecture', 'pipeline-stages'],
    },
    {
      type: 'category',
      label: 'Review Sistemi',
      items: ['multi-critic-approach', 'scoring-system', 'cross-reference'],
    },
    {
      type: 'category',
      label: 'Optimizasyon',
      items: ['pipeline-optimization', 'simulator', 'rescore-mode'],
    },
    {
      type: 'category',
      label: 'Entegrasyonlar',
      items: ['jira-integration', 'web-dashboard', 'litellm-proxy'],
    },
    {
      type: 'category',
      label: 'Operasyon',
      items: ['cli-reference', 'self-healing', 'configuration'],
    },
  ],
};

export default sidebars;
