import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

const config: Config = {
  title: 'dev-pipeline',
  tagline: 'Human-in-the-Loop Development Pipeline',
  favicon: 'img/favicon.ico',

  future: {
    v4: true,
  },

  url: 'https://ekintkara.github.io',
  baseUrl: '/doc-quailty-gate/',

  organizationName: 'ekintkara',
  projectName: 'doc-quailty-gate',

  onBrokenLinks: 'warn',
  onBrokenMarkdownLinks: 'warn',

  i18n: {
    defaultLocale: 'tr',
    locales: ['tr'],
  },

  presets: [
    [
      'classic',
      {
        docs: {
          id: 'default',
          path: 'docs/skill',
          routeBasePath: 'docs',
          sidebarPath: './sidebars.ts',
          editUrl: 'https://github.com/ekintkara/doc-quailty-gate/tree/main/website/',
        },
        blog: false,
        theme: {
          customCss: './src/css/custom.css',
        },
      } satisfies Preset.Options,
    ],
  ],

  plugins: [
    [
      '@docusaurus/plugin-content-docs',
      {
        id: 'dqg',
        path: 'docs-dqg',
        routeBasePath: 'dqg',
        sidebarPath: './sidebars-dqg.ts',
        editUrl: 'https://github.com/ekintkara/doc-quailty-gate/tree/main/website/',
      },
    ],
  ],

  themeConfig: {
    image: 'img/dqg-social-card.png',
    colorMode: {
      respectPrefersColorScheme: true,
    },
    navbar: {
      title: 'dev-pipeline',
      logo: {
        alt: 'dev-pipeline',
        src: 'img/logo.svg',
      },
      items: [
        {
          type: 'docSidebar',
          sidebarId: 'skillSidebar',
          position: 'left',
          label: 'Skill',
        },
        {
          type: 'docSidebar',
          sidebarId: 'dqgSidebar',
          position: 'left',
          label: 'DQG Engine',
          docsPluginId: 'dqg',
        },
        {
          href: 'https://github.com/ekintkara/doc-quailty-gate',
          label: 'GitHub',
          position: 'right',
        },
      ],
    },
    footer: {
      style: 'dark',
      links: [
        {
          title: 'Skill',
          items: [
            {
              label: 'Genel Bakis',
              to: '/docs/',
            },
            {
              label: 'Hizli Baslangic',
              to: '/docs/quick-start',
            },
          ],
        },
        {
          title: 'DQG Engine',
          items: [
            {
              label: 'Pipeline Stages',
              to: '/dqg/pipeline-stages',
            },
            {
              label: 'Scoring System',
              to: '/dqg/scoring-system',
            },
          ],
        },
        {
          title: 'Kaynaklar',
          items: [
            {
              label: 'CLI Referansi',
              to: '/dqg/cli-reference',
            },
            {
              label: 'Konfigurasyon',
              to: '/dqg/configuration',
            },
            {
              label: 'GitHub',
              href: 'https://github.com/ekintkara/doc-quailty-gate',
            },
          ],
        },
      ],
      copyright: `Copyright © ${new Date().getFullYear()} Doc Quality Gate. Built with Docusaurus.`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
      additionalLanguages: ['powershell', 'json', 'yaml'],
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
