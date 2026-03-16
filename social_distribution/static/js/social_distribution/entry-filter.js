'use strict'; 


function initEntryFilter(containerSelector) {
    document.querySelectorAll(containerSelector).forEach(container => {
        var fab = container.querySelector('.entry-filter-button'); 
        var slidingTray = container.querySelector('.entry-filter-button-tray');
        var toggle = container.querySelector('.entry-filter-button-toggle'); 
        var opts = container.querySelector('.entry-filter-button-options');
        var subopts = container.querySelector('.entry-filter-button-suboptions'); 
        var entryList = container.querySelector('.entries');
        var subdiv = container.querySelector('.entry-filter-button-subdiv');
        var label = container.querySelector('.entry-filter-button-label');

        if (!fab || !toggle || !opts || !entryList) return; 

        var currFilter = 'all'; 
        var subFilter = 'all'; 

        function updateLabel() {
            if (!label) return;
            
            var text = '';
            label.classList.remove('label-github');
 
            if (currentFilter === 'all') {
                text = '';
            } else if (currentFilter === 'github') {
                text = 'GitHub';
                label.classList.add('label-github');
            } else if (currentFilter === 'native') {
                if (currentSubfilter === 'all') {
                    text = 'Posts';
                } else {
                    text = currentSubfilter.charAt(0) + currentSubfilter.slice(1).toLowerCase();
                }
            }

            label.textContent = text;
            label.style.display = text ? '' : 'none';
        }

        // Listen for the toggle button
        toggle.addEventListener('click', function(e) {
            e.stopPropagation();
            fab.classList.toggle('fab-open');
        }); 
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
 
                updateLabel();
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
 
                    updateLabel();
                });
            });
        }
 
        // filter state preserved
        document.addEventListener('click', function(e) {
            if (fab && !fab.contains(e.target)) {
                fab.classList.remove('fab-open');
            }
        });
        updateLabel();
    });
}
 