import '../css/main.css';
import Alpine from 'alpinejs';
import 'htmx.org/dist/htmx.min.js';
import "cally";
import { Observer } from 'tailwindcss-intersect';

window.Alpine = Alpine;
Alpine.start();

// Start the intersection observer for scroll animations
Observer.start();