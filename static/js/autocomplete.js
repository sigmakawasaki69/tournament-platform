/**
 * Premium Autocomplete Component
 * Handles dynamic suggestions with debouncing and keyboard navigation.
 */
class Autocomplete {
    constructor(inputElement, options = {}) {
        this.input = inputElement;
        this.endpoint = options.endpoint || '';
        this.onSelect = options.onSelect || (() => {});
        this.minLength = options.minLength || 2;
        this.delay = options.delay || 300;
        
        this.container = null;
        this.results = [];
        this.selectedIndex = -1;
        this.timeout = null;

        this.init();
    }

    init() {
        // Ensure input is positioned for dropdown
        const wrapper = document.createElement('div');
        wrapper.className = 'autocomplete-wrapper';
        this.input.parentNode.insertBefore(wrapper, this.input);
        wrapper.appendChild(this.input);

        this.input.setAttribute('autocomplete', 'off');
        
        this.container = document.createElement('div');
        this.container.className = 'autocomplete-dropdown';
        wrapper.appendChild(this.container);

        this.input.addEventListener('input', () => this.handleInput());
        this.input.addEventListener('keydown', (e) => this.handleKeydown(e));
        
        // Close on blur, but delay to allow clicks
        this.input.addEventListener('blur', () => {
            setTimeout(() => this.close(), 200);
        });
    }

    handleInput() {
        clearTimeout(this.timeout);
        const value = this.input.value.trim();

        if (value.length < this.minLength) {
            this.close();
            return;
        }

        this.timeout = setTimeout(() => {
            this.fetchResults(value);
        }, this.delay);
    }

    async fetchResults(query) {
        try {
            const response = await fetch(`${this.endpoint}?q=${encodeURIComponent(query)}`);
            this.results = await response.json();
            
            if (this.results.length > 0) {
                this.render();
            } else {
                this.close();
            }
        } catch (error) {
            console.error('Autocomplete fetch error:', error);
        }
    }

    render() {
        this.container.innerHTML = '';
        this.selectedIndex = -1;

        this.results.forEach((item, index) => {
            const row = document.createElement('div');
            row.className = 'autocomplete-item';
            row.textContent = item;
            row.addEventListener('click', () => this.select(item));
            row.addEventListener('mouseenter', () => this.highlight(index));
            this.container.appendChild(row);
        });

        this.container.classList.add('visible');
    }

    handleKeydown(e) {
        if (!this.container.classList.contains('visible')) return;

        if (e.key === 'ArrowDown') {
            e.preventDefault();
            this.highlight(this.selectedIndex + 1);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            this.highlight(this.selectedIndex - 1);
        } else if (e.key === 'Enter') {
            if (this.selectedIndex > -1) {
                e.preventDefault();
                this.select(this.results[this.selectedIndex]);
            }
        } else if (e.key === 'Escape') {
            this.close();
        }
    }

    highlight(index) {
        const items = this.container.querySelectorAll('.autocomplete-item');
        if (items.length === 0) return;

        // Wrap around
        if (index >= items.length) index = 0;
        if (index < 0) index = items.length - 1;

        if (this.selectedIndex > -1) {
            items[this.selectedIndex].classList.remove('active');
        }

        this.selectedIndex = index;
        items[this.selectedIndex].classList.add('active');
        items[this.selectedIndex].scrollIntoView({ block: 'nearest' });
    }

    select(item) {
        this.input.value = item;
        this.onSelect(item);
        this.close();
    }

    close() {
        this.container.classList.remove('visible');
        this.selectedIndex = -1;
    }
}

// Global initialization helper
window.initAutocomplete = function(selector, options) {
    const el = document.querySelector(selector);
    if (el) return new Autocomplete(el, options);
    return null;
};
