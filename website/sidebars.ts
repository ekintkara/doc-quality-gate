import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  skillSidebar: [
    {
      type: 'category',
      label: 'Baslangic',
      items: ['overview', 'quick-start'],
    },
    {
      type: 'category',
      label: 'Pipeline Fazlari',
      items: [
        'phases',
        'task-intake',
        'impl-doc',
        'dqg-review',
        'planning',
        'implementation',
        'testing',
      ],
    },
    {
      type: 'category',
      label: 'Yapilandirma',
      items: ['configuration'],
    },
    {
      type: 'category',
      label: 'Operasyon',
      items: ['troubleshooting'],
    },
  ],
};

export default sidebars;
