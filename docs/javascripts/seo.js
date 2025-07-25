/* SEO enhancements for Meraki Dashboard Exporter documentation */

document.addEventListener('DOMContentLoaded', function() {
  addStructuredData();
  enhanceMetaTags();
  addOpenGraphTags();
  addTwitterCardTags();
  addCanonicalURL();
});

// Add JSON-LD structured data
function addStructuredData() {
  const structuredData = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    "name": "Meraki Dashboard Exporter",
    "applicationCategory": "Network Monitoring Software",
    "operatingSystem": "Linux, Docker",
    "description": "A high-performance Prometheus exporter for Cisco Meraki Dashboard API metrics with comprehensive monitoring capabilities and OpenTelemetry support",
    "url": "https://rknightion.github.io/meraki-dashboard-exporter/",
    "downloadUrl": "https://github.com/rknightion/meraki-dashboard-exporter",
    "softwareVersion": "latest",
    "programmingLanguage": "Python",
    "license": "https://github.com/rknightion/meraki-dashboard-exporter/blob/main/LICENSE",
    "author": {
      "@type": "Person",
      "name": "Rob Knighton",
      "url": "https://github.com/rknightion"
    },
    "maintainer": {
      "@type": "Person",
      "name": "Rob Knighton",
      "url": "https://github.com/rknightion"
    },
    "codeRepository": "https://github.com/rknightion/meraki-dashboard-exporter",
    "programmingLanguage": [
      "Python",
      "Docker",
      "YAML"
    ],
    "runtimePlatform": [
      "Docker",
      "Kubernetes",
      "Linux"
    ],
    "applicationSubCategory": [
      "Network Monitoring",
      "Prometheus Exporter",
      "Cisco Meraki",
      "Observability"
    ],
    "offers": {
      "@type": "Offer",
      "price": "0",
      "priceCurrency": "USD"
    },
    "screenshot": "https://rknightion.github.io/meraki-dashboard-exporter/assets/dashboard-preview.png",
    "featureList": [
      "Multi-tier metric collection system",
      "27+ specialized collectors for Meraki devices",
      "OpenTelemetry support",
      "Docker container deployment",
      "Comprehensive error handling",
      "Rate limiting and API optimization",
      "Production-ready monitoring"
    ]
  };

  // Add documentation-specific structured data
  const docData = {
    "@context": "https://schema.org",
    "@type": "TechArticle",
    "headline": document.title,
    "description": document.querySelector('meta[name="description"]')?.content || "Meraki Dashboard Exporter documentation",
    "url": window.location.href,
    "datePublished": document.querySelector('meta[name="date"]')?.content,
    "dateModified": document.querySelector('meta[name="git-revision-date-localized"]')?.content,
    "author": {
      "@type": "Person",
      "name": "Rob Knighton"
    },
    "publisher": {
      "@type": "Organization",
      "name": "Meraki Dashboard Exporter",
      "url": "https://rknightion.github.io/meraki-dashboard-exporter/"
    },
    "mainEntityOfPage": {
      "@type": "WebPage",
      "@id": window.location.href
    },
    "articleSection": getDocumentationSection(),
    "keywords": getPageKeywords(),
    "about": {
      "@type": "SoftwareApplication",
      "name": "Meraki Dashboard Exporter"
    }
  };

  // Insert structured data
  const script1 = document.createElement('script');
  script1.type = 'application/ld+json';
  script1.textContent = JSON.stringify(structuredData);
  document.head.appendChild(script1);

  const script2 = document.createElement('script');
  script2.type = 'application/ld+json';
  script2.textContent = JSON.stringify(docData);
  document.head.appendChild(script2);
}

// Enhance existing meta tags
function enhanceMetaTags() {
  // Add robots meta if not present
  if (!document.querySelector('meta[name="robots"]')) {
    addMetaTag('name', 'robots', 'index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1');
  }

  // Add language meta
  addMetaTag('name', 'language', 'en');

  // Add content type
  addMetaTag('http-equiv', 'Content-Type', 'text/html; charset=utf-8');

  // Add viewport if not present (should be handled by Material theme)
  if (!document.querySelector('meta[name="viewport"]')) {
    addMetaTag('name', 'viewport', 'width=device-width, initial-scale=1');
  }

  // Add keywords based on page content
  const keywords = getPageKeywords();
  if (keywords) {
    addMetaTag('name', 'keywords', keywords);
  }

  // Add article tags for documentation pages
  if (isDocumentationPage()) {
    addMetaTag('name', 'article:tag', 'prometheus');
    addMetaTag('name', 'article:tag', 'monitoring');
    addMetaTag('name', 'article:tag', 'cisco-meraki');
    addMetaTag('name', 'article:tag', 'network-monitoring');
  }
}

// Add Open Graph tags
function addOpenGraphTags() {
  const title = document.title || 'Meraki Dashboard Exporter';
  const description = document.querySelector('meta[name="description"]')?.content ||
    'High-performance Prometheus exporter for Cisco Meraki Dashboard API metrics';
  const url = window.location.href;
  const siteName = 'Meraki Dashboard Exporter Documentation';

  addMetaTag('property', 'og:type', 'website');
  addMetaTag('property', 'og:site_name', siteName);
  addMetaTag('property', 'og:title', title);
  addMetaTag('property', 'og:description', description);
  addMetaTag('property', 'og:url', url);
  addMetaTag('property', 'og:locale', 'en_US');
  addMetaTag('property', 'og:image', 'https://rknightion.github.io/meraki-dashboard-exporter/assets/og-image.png');
  addMetaTag('property', 'og:image:width', '1200');
  addMetaTag('property', 'og:image:height', '630');
  addMetaTag('property', 'og:image:alt', 'Meraki Dashboard Exporter - Prometheus metrics for Cisco Meraki');
}

// Add Twitter Card tags
function addTwitterCardTags() {
  const title = document.title || 'Meraki Dashboard Exporter';
  const description = document.querySelector('meta[name="description"]')?.content ||
    'High-performance Prometheus exporter for Cisco Meraki Dashboard API metrics';

  addMetaTag('name', 'twitter:card', 'summary_large_image');
  addMetaTag('name', 'twitter:title', title);
  addMetaTag('name', 'twitter:description', description);
  addMetaTag('name', 'twitter:image', 'https://rknightion.github.io/meraki-dashboard-exporter/assets/twitter-card.png');
  addMetaTag('name', 'twitter:creator', '@rknightion');
  addMetaTag('name', 'twitter:site', '@rknightion');
}

// Add canonical URL
function addCanonicalURL() {
  if (!document.querySelector('link[rel="canonical"]')) {
    const canonical = document.createElement('link');
    canonical.rel = 'canonical';
    canonical.href = window.location.href;
    document.head.appendChild(canonical);
  }
}

// Helper functions
function addMetaTag(attribute, name, content) {
  if (!document.querySelector(`meta[${attribute}="${name}"]`)) {
    const meta = document.createElement('meta');
    meta.setAttribute(attribute, name);
    meta.content = content;
    document.head.appendChild(meta);
  }
}

function getDocumentationSection() {
  const path = window.location.pathname;
  if (path.includes('/metrics/')) return 'Metrics Reference';
  if (path.includes('/collectors/')) return 'Collector Reference';
  if (path.includes('/config/')) return 'Configuration';
  if (path.includes('/deployment/')) return 'Deployment';
  if (path.includes('/adr/')) return 'Architecture Decisions';
  if (path.includes('/patterns/')) return 'Development Patterns';
  return 'Documentation';
}

function getPageKeywords() {
  const path = window.location.pathname;
  const title = document.title.toLowerCase();
  const content = document.body.textContent.toLowerCase();

  let keywords = ['meraki', 'prometheus', 'exporter', 'monitoring', 'cisco'];

  // Add path-specific keywords
  if (path.includes('/metrics/')) keywords.push('metrics', 'telemetry', 'observability');
  if (path.includes('/collectors/')) keywords.push('collectors', 'data collection', 'api');
  if (path.includes('/config/')) keywords.push('configuration', 'environment variables', 'setup');
  if (path.includes('/deployment/')) keywords.push('deployment', 'docker', 'kubernetes', 'production');
  if (path.includes('/getting-started/')) keywords.push('installation', 'quick start', 'tutorial');

  // Add device type keywords if mentioned
  if (content.includes('wireless') || content.includes('access point')) keywords.push('wireless', 'access-points', 'mr');
  if (content.includes('switch')) keywords.push('switches', 'ms');
  if (content.includes('security appliance')) keywords.push('security-appliances', 'mx');
  if (content.includes('sensor')) keywords.push('sensors', 'mt', 'environmental');
  if (content.includes('camera')) keywords.push('cameras', 'mv', 'security');
  if (content.includes('cellular')) keywords.push('cellular', 'mg', 'gateway');

  return keywords.join(', ');
}

function isDocumentationPage() {
  return !window.location.pathname.endsWith('/') ||
         window.location.pathname.includes('/docs/');
}
