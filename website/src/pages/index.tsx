import type {ReactNode} from 'react';
import clsx from 'clsx';
import Link from '@docusaurus/Link';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import Layout from '@theme/Layout';
import Heading from '@theme/Heading';
import styles from './index.module.css';

const features = [
  {
    title: 'Human-in-the-Loop',
    description: 'Her fazda AI durur, ozet sunar, sizin onayinizi bekler.',
    icon: '\u{1F91D}',
  },
  {
    title: 'Multi-Source Task',
    description: 'Jira, Azure DevOps, GitHub Issues, dosya veya serbest metin.',
    icon: '\u{1F4CB}',
  },
  {
    title: 'DQG-Powered Review',
    description: 'Doc Quality Gate ile dokumaninizi kod tabaniniza karsi dogrular.',
    icon: '\u{1F50D}',
  },
  {
    title: 'Multi-Agent Review',
    description: '3 paralel agent + Judge ile TODO ve implementation review.',
    icon: '\u{1F9E0}',
  },
  {
    title: 'Implementation Review',
    description: 'Compliance, Quality, Pattern perspektiflerinden kod review.',
    icon: '\u26A1',
  },
  {
    title: 'Pipeline Takibi',
    description: '11 faz, state dosyasi, resume destegi.',
    icon: '\u{1F4CA}',
  },
];

function HomepageHeader(): ReactNode {
  const {siteConfig} = useDocusaurusContext();
  return (
    <header className={clsx('hero hero--primary', styles.heroBanner)}>
      <div className="container">
        <Heading as="h1" className="hero__title">
          {siteConfig.title}
        </Heading>
        <p className="hero__subtitle">{siteConfig.tagline}</p>
        <p className={styles.heroDescription}>
          Kod yazmadan once dokumaninizi review edin. Her adimda sizin onayiniz.
        </p>
        <div className={styles.buttons}>
          <Link className="button button--secondary button--lg" to="/docs/">
            Skill Dokumantasyonu
          </Link>
          <Link className="button button--outline button--secondary button--lg" to="/dqg/overview">
            DQG Engine Referans
          </Link>
        </div>
      </div>
    </header>
  );
}

function Feature({title, description, icon}: {title: string; description: string; icon: string}): ReactNode {
  return (
    <div className={clsx('col col--4', styles.feature)}>
      <div className={styles.featureIcon}>{icon}</div>
      <h3>{title}</h3>
      <p>{description}</p>
    </div>
  );
}

export default function Home(): ReactNode {
  const {siteConfig} = useDocusaurusContext();
  return (
    <Layout title={siteConfig.title} description="Human-in-the-Loop Development Pipeline">
      <HomepageHeader />
      <main>
        <section className={styles.features}>
          <div className="container">
            <div className="row">
              {features.map((props, idx) => (
                <Feature key={idx} {...props} />
              ))}
            </div>
          </div>
        </section>
        <section className={styles.pipelineSection}>
          <div className="container">
            <h2 className={styles.sectionTitle}>Pipeline Akisi</h2>
            <div className={styles.pipelineFlow}>
              <div className={styles.pipelineStep}>Task Intake</div>
              <div className={styles.pipelineArrow}>{'\u2192'}</div>
              <div className={styles.pipelineStep}>Impl Doc</div>
              <div className={styles.pipelineArrow}>{'\u2192'}</div>
              <div className={styles.pipelineStep}>DQG Review</div>
              <div className={styles.pipelineArrow}>{'\u2192'}</div>
              <div className={styles.pipelineStep}>Plan</div>
              <div className={styles.pipelineArrow}>{'\u2192'}</div>
              <div className={styles.pipelineStep}>Implement</div>
              <div className={styles.pipelineArrow}>{'\u2192'}</div>
              <div className={styles.pipelineStep}>Review</div>
              <div className={styles.pipelineArrow}>{'\u2192'}</div>
              <div className={styles.pipelineStep}>Test</div>
              <div className={styles.pipelineArrow}>{'\u2192'}</div>
              <div className={clsx(styles.pipelineStep, styles.pipelineStepFinal)}>Done</div>
            </div>
          </div>
        </section>
      </main>
    </Layout>
  );
}