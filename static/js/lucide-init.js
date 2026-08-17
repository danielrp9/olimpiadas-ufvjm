/**
 * Lucide Icons Initialization & Custom Icons Integration
 * System: Olimpíadas UFVJM
 */
(function () {
    // Custom Brand and Social Icons formatted for Lucide
    const customIcons = {
        Linkedin: [
            ["path", { d: "M16 8a6 6 0 0 1 6 6v7h-4v-7a2 2 0 0 0-2-2 2 2 0 0 0-2 2v7h-4v-7a6 6 0 0 1 6-6z" }],
            ["rect", { width: "4", height: "12", x: "2", y: "9" }],
            ["circle", { cx: "4", cy: "4", r: "2" }]
        ],
        Instagram: [
            ["rect", { width: "20", height: "20", x: "2", y: "2", rx: "5", ry: "5" }],
            ["path", { d: "M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z" }],
            ["line", { x1: "17.5", x2: "17.51", y1: "6.5", y2: "6.5" }]
        ],
        Twitter: [
            ["path", { d: "M22 4s-.7 2.1-2 3.4c1.6 10-9.4 17.3-18 11.6 2.2.1 4.4-.6 6-2C3 15.5.5 9.6 3 5c2.2 2.6 5.6 4.1 9 4-.9-4.2 4-6.6 7-3.8 1.1 0 3-1.2 3-1.2z" }]
        ],
        XTwitter: [
            ["path", { d: "M4 4l11.733 16h4.267l-11.733-16z" }],
            ["path", { d: "M4 20l6.768-6.768m2.464-2.464l6.768-6.768" }]
        ],
        Whatsapp: [
            ["path", { d: "M3 21l1.65-3.8a9 9 0 1 1 3.4 2.9L3 21" }],
            ["path", { d: "M9 10a.5.5 0 0 0 1 0V9a.5.5 0 0 0-1 0v1a5 5 0 0 0 5 5h1a.5.5 0 0 0 0-1h-1a.5.5 0 0 0 0 1" }]
        ]
    };

    // FontAwesome to Lucide Name Map for dynamic / backwards compatibility
    const FA_TO_LUCIDE = {
        'address-card': 'contact',
        'archive': 'archive',
        'arrow-left': 'arrow-left',
        'arrow-right': 'arrow-right',
        'balance-scale': 'scale',
        'ban': 'ban',
        'bars': 'menu',
        'basketball': 'circle-dot',
        'bell': 'bell',
        'bell-slash': 'bell-off',
        'calculator': 'calculator',
        'calendar-alt': 'calendar',
        'calendar-check': 'calendar-check',
        'calendar-plus': 'calendar-plus',
        'calendar-times': 'calendar-x',
        'certificate': 'award',
        'chart-bar': 'bar-chart-3',
        'chart-line': 'line-chart',
        'chart-pie': 'pie-chart',
        'check': 'check',
        'check-circle': 'check-circle-2',
        'check-double': 'check-check',
        'chess': 'crown',
        'chevron-down': 'chevron-down',
        'chevron-left': 'chevron-left',
        'chevron-right': 'chevron-right',
        'chevron-up': 'chevron-up',
        'circle': 'circle',
        'circle-notch': 'loader-2',
        'clock': 'clock',
        'coffee': 'coffee',
        'cog': 'settings',
        'comment-alt': 'message-square',
        'comment-dots': 'message-square-more',
        'comments': 'messages-square',
        'copy': 'copy',
        'crown': 'crown',
        'drumstick-bite': 'drumstick',
        'edit': 'pencil',
        'envelope': 'mail',
        'envelope-open-text': 'mail-open',
        'exchange-alt': 'arrow-left-right',
        'exclamation-circle': 'alert-circle',
        'exclamation-triangle': 'alert-triangle',
        'external-link-alt': 'external-link',
        'eye': 'eye',
        'eye-slash': 'eye-off',
        'file-alt': 'file-text',
        'file-excel': 'file-spreadsheet',
        'file-export': 'file-up',
        'file-invoice': 'file-text',
        'file-invoice-dollar': 'receipt',
        'file-pdf': 'file-text',
        'file-signature': 'signature',
        'filter': 'filter',
        'fingerprint': 'fingerprint',
        'flag': 'flag',
        'flag-checkered': 'flag-triangle-right',
        'folder-open': 'folder-open',
        'futbol': 'circle-dot',
        'gavel': 'gavel',
        'genderless': 'circle',
        'globe': 'globe',
        'graduation-cap': 'graduation-cap',
        'hand-paper': 'hand',
        'history': 'history',
        'id-badge': 'badge-check',
        'id-card': 'id-card',
        'info-circle': 'info',
        'instagram': 'instagram',
        'layer-group': 'layers',
        'link': 'link',
        'linkedin': 'linkedin',
        'list-alt': 'list-todo',
        'list-ol': 'list-ordered',
        'lock': 'lock',
        'magic': 'wand-2',
        'map-marker-alt': 'map-pin',
        'map-pin': 'map-pin',
        'mars': 'circle-user',
        'microchip': 'cpu',
        'moon': 'moon',
        'paper-plane': 'send',
        'pen': 'pen-line',
        'pencil-alt': 'pencil',
        'play': 'play',
        'plus': 'plus',
        'plus-circle': 'plus-circle',
        'power-off': 'power',
        'print': 'printer',
        'random': 'shuffle',
        'redo-alt': 'rotate-cw',
        'reply': 'reply',
        'robot': 'bot',
        'running': 'activity',
        'save': 'save',
        'search': 'search',
        'share-nodes': 'share-2',
        'shield-alt': 'shield',
        'sign-in-alt': 'log-in',
        'sign-out-alt': 'log-out',
        'sitemap': 'network',
        'sliders-h': 'sliders-horizontal',
        'spinner': 'loader-2',
        'star': 'star',
        'table-tennis': 'activity',
        'terminal': 'terminal',
        'times': 'x',
        'times-circle': 'x-circle',
        'trash-alt': 'trash-2',
        'trophy': 'trophy',
        'undo-alt': 'rotate-ccw',
        'university': 'landmark',
        'upload': 'upload',
        'user-check': 'user-check',
        'user-edit': 'user-cog',
        'user-friends': 'users',
        'user-minus': 'user-minus',
        'user-plus': 'user-plus',
        'user-shield': 'shield-check',
        'user-slash': 'user-x',
        'user-tie': 'user-check',
        'users': 'users',
        'users-cog': 'users',
        'utensils': 'utensils',
        'venus': 'circle-user',
        'venus-mars': 'users-2',
        'volleyball': 'circle-dot',
        'whatsapp': 'whatsapp',
        'x-twitter': 'twitter'
    };

    function initLucide() {
        if (typeof lucide === 'undefined') return;

        const allIcons = {
            ...lucide.icons,
            ...customIcons
        };

        const originalCreateIcons = lucide.createIcons;
        lucide.createIcons = function (options = {}) {
            const root = options.root || document;
            
            // Backward compatibility scan for any remaining fa-* classes
            if (root && root.querySelectorAll) {
                const legacyElements = root.querySelectorAll('i[class*="fa-"]:not([data-lucide])');
                legacyElements.forEach(el => {
                    const classList = Array.from(el.classList);
                    for (const cls of classList) {
                        if (cls.startsWith('fa-')) {
                            const name = cls.substring(3);
                            if (name === 'spin') {
                                el.classList.add('animate-spin');
                            } else if (FA_TO_LUCIDE[name]) {
                                el.setAttribute('data-lucide', FA_TO_LUCIDE[name]);
                                el.classList.remove('fas', 'far', 'fab', 'fa', cls);
                                break;
                            }
                        }
                    }
                });
            }

            return originalCreateIcons.call(lucide, {
                icons: allIcons,
                ...options
            });
        };

        window.refreshLucideIcons = function (targetRoot) {
            try {
                lucide.createIcons({ root: targetRoot || document });
            } catch (e) {
                console.error('[Lucide Init Error]', e);
            }
        };

        // Run initial icon creation
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => window.refreshLucideIcons());
        } else {
            window.refreshLucideIcons();
        }

        // Automatic MutationObserver to render icons in dynamic content
        if (typeof MutationObserver !== 'undefined') {
            let debounceTimer = null;
            const observer = new MutationObserver(mutations => {
                let hasNewIcons = false;
                for (const mutation of mutations) {
                    if (mutation.addedNodes && mutation.addedNodes.length > 0) {
                        for (const node of mutation.addedNodes) {
                            if (node.nodeType === 1) { // ELEMENT_NODE
                                if (node.hasAttribute('data-lucide') || node.querySelector?.('[data-lucide], i[class*="fa-"]')) {
                                    hasNewIcons = true;
                                    break;
                                }
                            }
                        }
                    }
                    if (hasNewIcons) break;
                }
                if (hasNewIcons) {
                    if (debounceTimer) cancelAnimationFrame(debounceTimer);
                    debounceTimer = requestAnimationFrame(() => {
                        window.refreshLucideIcons();
                    });
                }
            });

            observer.observe(document.body || document.documentElement, {
                childList: true,
                subtree: true
            });
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initLucide);
    } else {
        initLucide();
    }
})();
