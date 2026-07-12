const documents = [
  { path: '01-PLAN.md', id: '01-开发计划' },
  { path: '02-ARCHITECTURE.md', id: '02-系统架构与安全边界' },
  { path: '03-ENVIRONMENT_CHECK.md', id: '03-算力平台环境检查结果' },
  { path: '04-COLLABORATION.md', id: '04-四人团队协作方案' },
  { path: '05-DIRECTORY-STRUCTURE.md', id: '05-项目目录规范' },
];

const content = document.querySelector('#doc-content');
const loadingState = document.querySelector('#loading-state');
const emptyResult = document.querySelector('#empty-result');
const search = document.querySelector('#doc-search');
const searchStatus = document.querySelector('#search-status');
const navLinks = [...document.querySelectorAll('.chapter-nav a')];
let chapters = [];

function normalize(value) {
  return value.trim().toLocaleLowerCase('zh-CN');
}

function filterChapters() {
  const query = normalize(search.value);
  let visible = 0;

  for (const item of chapters) {
    const matches = !query || normalize(item.textContent).includes(query);
    item.hidden = !matches;
    if (matches) visible += 1;
  }

  emptyResult.hidden = visible !== 0;
  searchStatus.textContent = query ? `找到 ${visible} 个章节` : `${chapters.length} 个章节`;
}

function observeChapters() {
  const observer = new IntersectionObserver((entries) => {
    const visible = entries
      .filter((entry) => entry.isIntersecting)
      .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
    if (!visible) return;

    for (const link of navLinks) {
      link.classList.toggle('active', link.hash === `#${visible.target.id}`);
    }
  }, { rootMargin: '-12% 0px -72% 0px', threshold: [0, .1, .5] });

  chapters.forEach((item) => observer.observe(item));
}

async function loadDocuments() {
  try {
    if (!window.marked) throw new Error('Markdown 解析器未加载');

    const responses = await Promise.all(documents.map(async (document) => {
      const response = await fetch(document.path);
      if (!response.ok) throw new Error(`${document.path}: HTTP ${response.status}`);
      return {
        ...document,
        markdown: await response.text(),
      };
    }));

    loadingState.remove();
    for (const item of responses) {
      const chapter = document.createElement('section');
      chapter.className = 'chapter';
      chapter.id = item.id;
      chapter.innerHTML = marked.parse(item.markdown);
      content.insertBefore(chapter, emptyResult);
      chapters.push(chapter);
    }

    content.setAttribute('aria-busy', 'false');
    search.disabled = false;
    searchStatus.textContent = `${chapters.length} 个章节`;
    search.addEventListener('input', filterChapters);
    observeChapters();

    if (location.hash) {
      document.getElementById(decodeURIComponent(location.hash.slice(1)))?.scrollIntoView();
    }
  } catch (error) {
    content.setAttribute('aria-busy', 'false');
    loadingState.innerHTML = `
      <strong>文档加载失败</strong>
      <span>${error.message}</span>
      <span>请通过 GitHub Pages 或本地 HTTP 服务打开，不要直接双击 HTML 文件。</span>
    `;
    searchStatus.textContent = '加载失败';
  }
}

loadDocuments();
