
const menuToggle = document.getElementById("menu-toggle");
const navMenu = document.getElementById("nav-menu");

// Mobile navigation
menuToggle.addEventListener("click", () => {
    navMenu.classList.toggle("active");
});

// Close menu after clicking a link
document.querySelectorAll("#nav-menu a").forEach(link => {
    link.addEventListener("click", () => {
        navMenu.classList.remove("active");
    });
});

// Automatically update copyright year
document.getElementById("year").textContent =
    new Date().getFullYear();
