'use strict'; 


function initEntryFilter(containerSelector) {
    document.querySelectorAll(containerSelector).forEach(container => {
        var fab = container.querySelector('.entry-filter-button'); 
        var opts = container.querySelector('.entry-filter-button-options');
        var subopts = container.querySelector('.entry-filter-button-suboptions'); 
        var entryList = container.querySelector('.entries');
        var subdiv = container.querySelector('.entry-filter-button-subdiv');

        if (!fab || !opts || !entryList) return; 

        var currentFilter = 'all'; 
        var currentSubfilter = 'all'; 

       
        opts.querySelectorAll('button').forEach(function(btn) {
            btn.addEventListener('click', function(e) {
                e.stopPropagation();
                var filter = btn.dataset.filter;
                currentFilter = filter;
 
                // Update active states
                opts.querySelectorAll('button').forEach(function(b) {
                    b.classList.remove('active', 'active-github');
                });
                if (filter === 'github') {
                    btn.classList.add('active-github');
                } else {
                    btn.classList.add('active');
                }
 
                // pply filter to entry list
                entryList.classList.remove('filter-native', 'filter-github');
                if (filter !== 'all') {
                    entryList.classList.add('filter-' + filter);
                }
 
                // clr the sub-filter
                entryList.className = entryList.className.replace(/subfilter-\S+/g, '').trim();
                currentSubfilter = 'all';
 
                // display suboptions only for entries
                if (subopts) {
                    if (filter === 'native') {
                        subopts.classList.add('sub-open');
                        if (subdiv) subdiv.classList.add('sub-open');
                        subopts.querySelectorAll('button').forEach(function(sb) {
                            sb.classList.remove('active');
                        });
                        var allBtn = subopts.querySelector('[data-subfilter="all"]');
                        if (allBtn) allBtn.classList.add('active');
                    } else {
                        subopts.classList.remove('sub-open');
                        if (subdiv) subdiv.classList.remove('sub-open');
                    }
                }
 
            });
        });
 
        // sub filter options for native posts 
        if (subopts) {
            subopts.querySelectorAll('button').forEach(function(btn) {
                btn.addEventListener('click', function(e) {
                    e.stopPropagation();
                    var subfilter = btn.dataset.subfilter;
                    currentSubfilter = subfilter;
 
                    subopts.querySelectorAll('button').forEach(function(b) {
                        b.classList.remove('active');
                    });
                    btn.classList.add('active');
 
                    entryList.className = entryList.className.replace(/subfilter-\S+/g, '').trim();
                    if (subfilter !== 'all') {
                        entryList.classList.add('subfilter-' + subfilter);
                    }
 
                });
            });
        }
 
    });
}

function initViewToggle(containerSelector) {
    document.querySelectorAll(containerSelector).forEach(function(container) {
        var btn = container.querySelector('.view-toggle');
        var list = container.querySelector('.entries');

        if (!btn || !list) return;

        btn.addEventListener('click', function() {
            btn.classList.toggle('grid-active');
            list.classList.toggle('grid-view');
        });
    });
}
 

function initPeekTabs() {
    document.querySelectorAll('.entry-peek-tab').forEach(function(tab) {
        var card = tab.closest('.entry-card-link-wrapper').querySelector('.entry-card');
        if (!card) return;

        tab.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            card.classList.toggle('entry-expanded');
        });
    });
}