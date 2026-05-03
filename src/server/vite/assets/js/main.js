import '../css/main.css';
import Alpine from 'alpinejs';
import htmx from 'htmx.org/dist/htmx.esm.js';
import { Observer } from 'tailwindcss-intersect';

window.htmx = htmx;
window.Alpine = Alpine;
Alpine.start();

// Start the intersection observer for scroll animations
Observer.start();