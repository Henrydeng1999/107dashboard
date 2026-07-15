const documents = [
  { path: '01-PLAN.md', id: '01-开发计划', label: '开发计划' },
  { path: '02-ARCHITECTURE.md', id: '02-系统架构与安全边界', label: '系统架构' },
  { path: '03-ENVIRONMENT_CHECK.md', id: '03-算力平台环境检查结果', label: '环境检查' },
  { path: '04-COLLABORATION.md', id: '04-四人团队协作方案', label: '团队协作' },
  { path: '05-DIRECTORY-STRUCTURE.md', id: '05-项目目录规范', label: '目录规范' },
  { path: '06-PLATFORM-DEPLOYMENT.md', id: '06-算力平台部署与更新', label: '平台部署' },
  { path: '07-MVP-API-DESIGN.md', id: '07-MVP API 设计', label: 'API 设计' },
  { path: '08-PROGRESS-CHECKLIST.md', id: '08-项目完成情况检查表', label: '项目进度' },
];

const content = document.querySelector('#doc-content');
const loadingState = document.querySelector('#loading-state');
const search = document.querySelector('#doc-search');
const searchStatus = document.querySelector('#search-status');
const navLinks = [...document.querySelectorAll('.chapter-nav a')];
const markdownCache = new Map();
let activeDocument = null;
let renderSequence = 0;

function normalize(value) {
  return value.trim().toLocaleLowerCase('zh-CN');
}

function documentFromHash() {
  try {
    const id = decodeURIComponent(location.hash.slice(1));
    return documents.find((item) => item.id === id) ?? documents[0];
  } catch {
    return documents[0];
  }
}

async function readMarkdown(document) {
  if (markdownCache.has(document.path)) return markdownCache.get(document.path);

  const response = await fetch(document.path);
  if (!response.ok) throw new Error(`${document.path}: HTTP ${response.status}`);
  const markdown = await response.text();
  markdownCache.set(document.path, markdown);
  return markdown;
}

function setActiveNavigation(document) {
  for (const link of navLinks) {
    const id = decodeURIComponent(link.hash.slice(1));
    link.classList.toggle('active', id === document.id);
    if (id === document.id) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  }
}

function filterNavigation() {
  const query = normalize(search.value);
  let visible = 0;

  for (const link of navLinks) {
    const matches = !query || normalize(link.textContent).includes(query);
    link.hidden = !matches;
    if (matches) visible += 1;
  }

  searchStatus.textContent = query ? `找到 ${visible} 个章节` : `${documents.length} 个章节`;
}

function waitForFadeOut() {
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return Promise.resolve();
  content.classList.add('is-switching');
  return new Promise((resolve) => window.setTimeout(resolve, 170));
}

function fadeIn() {
  requestAnimationFrame(() => requestAnimationFrame(() => content.classList.remove('is-switching')));
}

async function showDocument(document, options = {}) {
  const { initial = false, updateHistory = true } = options;
  if (!initial && activeDocument?.id === document.id) return;

  const sequence = ++renderSequence;

  try {
    const [markdown] = await Promise.all([
      readMarkdown(document),
      initial ? Promise.resolve() : waitForFadeOut(),
    ]);
    if (sequence !== renderSequence) return;

    const chapter = documentNode(document, markdown);
    content.replaceChildren(chapter);
    activeDocument = document;
    setActiveNavigation(document);
    window.document.title = `${document.label} · 107 Dashboard`;

    if (updateHistory) history.pushState({ documentId: document.id }, '', `#${encodeURIComponent(document.id)}`);
    if (!initial) window.scrollTo({ top: 0, behavior: 'auto' });
    fadeIn();
  } catch (error) {
    content.classList.remove('is-switching');
    content.innerHTML = `
      <div class="loading-state">
        <strong>文档加载失败</strong>
        <span>${error.message}</span>
        <span>请通过 GitHub Pages 或本地 HTTP 服务打开，不要直接双击 HTML 文件。</span>
      </div>
    `;
  }
}

function documentNode(document, markdown) {
  const chapter = window.document.createElement('section');
  chapter.className = 'chapter';
  chapter.id = document.id;
  chapter.innerHTML = marked.parse(markdown);
  return chapter;
}

function handleDocumentLink(event) {
  const link = event.target.closest('a[href^="#"]');
  if (!link) return;

  const id = decodeURIComponent(link.hash.slice(1));
  const target = documents.find((item) => item.id === id);
  if (!target) return;

  event.preventDefault();
  showDocument(target);
}

async function initialize() {
  if (!window.marked) {
    loadingState.innerHTML = '<strong>文档加载失败</strong><span>Markdown 解析器未加载。</span>';
    return;
  }

  content.setAttribute('aria-busy', 'true');
  await showDocument(documentFromHash(), { initial: true, updateHistory: false });
  content.setAttribute('aria-busy', 'false');
  search.disabled = false;
  searchStatus.textContent = `${documents.length} 个章节`;
  search.addEventListener('input', filterNavigation);
  document.addEventListener('click', handleDocumentLink);
  window.addEventListener('popstate', () => showDocument(documentFromHash(), { updateHistory: false }));
}

initialize();
