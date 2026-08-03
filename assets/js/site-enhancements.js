(function () {
  'use strict';

  function makeDialog() {
    var dialog = document.createElement('dialog');
    dialog.className = 'bibtex-dialog';
    dialog.setAttribute('aria-labelledby', 'bibtex-dialog-title');
    dialog.innerHTML =
      '<div class="bibtex-dialog__header">' +
        '<h2 id="bibtex-dialog-title">BibTeX citation</h2>' +
        '<button class="bibtex-dialog__close" type="button" aria-label="Close BibTeX window">&times;</button>' +
      '</div>' +
      '<div class="bibtex-dialog__body">' +
        '<pre><code>Loading citation…</code></pre>' +
        '<button class="academic-button copy-bibtex" type="button">Copy BibTeX</button>' +
        '<span class="copy-status" role="status" aria-live="polite"></span>' +
      '</div>';
    document.body.appendChild(dialog);

    dialog.querySelector('.bibtex-dialog__close').addEventListener('click', function () { dialog.close(); });
    dialog.addEventListener('click', function (event) {
      if (event.target === dialog) dialog.close();
    });
    dialog.querySelector('.copy-bibtex').addEventListener('click', function () {
      var text = dialog.querySelector('code').textContent;
      if (!navigator.clipboard) {
        var selection = window.getSelection();
        var range = document.createRange();
        range.selectNodeContents(dialog.querySelector('code'));
        selection.removeAllRanges();
        selection.addRange(range);
        dialog.querySelector('.copy-status').textContent = 'Selected — press Ctrl/Cmd+C';
        return;
      }
      navigator.clipboard.writeText(text).then(function () {
        dialog.querySelector('.copy-status').textContent = 'Copied';
      }).catch(function () {
        dialog.querySelector('.copy-status').textContent = 'Select the text and copy manually';
      });
    });
    return dialog;
  }

  document.addEventListener('DOMContentLoaded', function () {
    var archive = document.querySelector('.archive');
    if (archive && window.location.pathname.indexOf('/publications') !== -1) {
      var headings = Array.prototype.slice.call(archive.querySelectorAll('h3'));
      var filters = document.createElement('nav');
      filters.className = 'publication-filters';
      filters.setAttribute('aria-label', 'Filter publications by type');
      filters.innerHTML = '<button type="button" class="active" data-filter="all" aria-pressed="true">All</button>' +
        '<button type="button" data-filter="books-chapters" aria-pressed="false">Books &amp; Chapters</button>' +
        '<button type="button" data-filter="patents" aria-pressed="false">Patents</button>' +
        '<button type="button" data-filter="journals" aria-pressed="false">Journals</button>' +
        '<button type="button" data-filter="conferences" aria-pressed="false">Conferences</button>';
      if (headings.length) archive.insertBefore(filters, headings[0]);

      var sections = headings.map(function (heading) {
        var name = heading.textContent.trim().toLowerCase().replace(/[^a-z]+/g, '-').replace(/(^-|-$)/g, '');
        var elements = [heading];
        var sibling = heading.nextElementSibling;
        while (sibling && sibling.tagName !== 'H3') {
          elements.push(sibling);
          sibling = sibling.nextElementSibling;
        }
        return { name: name, elements: elements };
      });

      filters.querySelectorAll('button').forEach(function (button) {
        button.addEventListener('click', function () {
          var selected = button.dataset.filter;
          filters.querySelectorAll('button').forEach(function (item) {
            var active = item === button;
            item.classList.toggle('active', active);
            item.setAttribute('aria-pressed', active ? 'true' : 'false');
          });
          sections.forEach(function (section) {
            var visible = selected === 'all' || section.name === selected;
            section.elements.forEach(function (element) { element.hidden = !visible; });
          });
        });
      });

      archive.querySelectorAll('a img[src*="shields.io"]').forEach(function (image) {
        var link = image.closest('a');
        if (!link || /\.txt$/i.test(link.href)) return;
        var label = image.alt || (link.href.indexOf('arxiv.org') !== -1 ? 'arXiv' : 'View paper');
        link.className = 'publication-link';
        link.textContent = label === 'Link' ? 'View paper' : label;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
      });
    }

    var bibLinks = document.querySelectorAll('.archive a[href$=".txt"]');
    if (!bibLinks.length) return;
    var dialog = makeDialog();
    var code = dialog.querySelector('code');
    var copyButton = dialog.querySelector('.copy-bibtex');
    var status = dialog.querySelector('.copy-status');

    bibLinks.forEach(function (link) {
      var button = document.createElement('button');
      button.type = 'button';
      button.className = 'bibtex-button';
      button.textContent = 'BibTeX';
      button.setAttribute('aria-label', 'View BibTeX citation');
      button.dataset.bibtexUrl = link.href;
      link.replaceWith(button);

      button.addEventListener('click', function () {
        code.textContent = 'Loading citation…';
        status.textContent = '';
        copyButton.disabled = true;
        dialog.showModal();
        fetch(button.dataset.bibtexUrl)
          .then(function (response) {
            if (!response.ok) throw new Error('Citation could not be loaded.');
            return response.text();
          })
          .then(function (text) { code.textContent = text.trim(); copyButton.disabled = false; })
          .catch(function (error) { code.textContent = error.message; });
      });
    });
  });
}());
