// Recommended Posts Carousel
document.addEventListener('DOMContentLoaded', function() {
    const carousel = document.getElementById('recommendedCarousel');
    const prevBtn = document.getElementById('prevRecommended');
    const nextBtn = document.getElementById('nextRecommended');

    if (!carousel || !prevBtn || !nextBtn) return;

    let currentIndex = 0;
    const items = carousel.children;
    const totalItems = items.length;
    const itemsPerView = 3;
    const maxIndex = Math.max(0, totalItems - itemsPerView);

    function updateCarousel() {
        const itemWidth = items[0].offsetWidth;
        const gap = 12;
        const offset = currentIndex * (itemWidth + gap);
        carousel.style.transform = `translateX(-${offset}px)`;

        prevBtn.style.opacity = currentIndex === 0 ? '0.5' : '1';
        prevBtn.style.cursor = currentIndex === 0 ? 'not-allowed' : 'pointer';
        nextBtn.style.opacity = currentIndex >= maxIndex ? '0.5' : '1';
        nextBtn.style.cursor = currentIndex >= maxIndex ? 'not-allowed' : 'pointer';
    }

    prevBtn.addEventListener('click', function() {
        if (currentIndex > 0) {
            currentIndex--;
            updateCarousel();
        }
    });

    nextBtn.addEventListener('click', function() {
        if (currentIndex < maxIndex) {
            currentIndex++;
            updateCarousel();
        }
    });

    updateCarousel();
});

// CSRF Token Helper
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

const csrftoken = getCookie('csrftoken');

// Favorite Toggle
document.querySelectorAll('.favorite-icon').forEach(icon => {
    icon.addEventListener('click', () => {
        const postId = icon.dataset.postId;

        fetch(`/saved/toggle/${postId}/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrftoken,
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(r => r.json())
        .then(data => {
            if (data.status === 'saved') {
                icon.textContent = 'favorite';
                icon.style.color = '#dc3545';
            } else {
                icon.textContent = 'favorite_border';
                icon.style.color = '#ccc';
            }
        })
        .catch(err => console.error(err));
    });
});

// Load AI Recommendations
document.addEventListener('DOMContentLoaded', function() {
    loadRecommendations('ai-recommendations-container', {
        limit: 8,
        strategy: 'switching',  // Tự động chọn thuật toán phù hợp
    });
});

// Helper function để load recommendations
function loadRecommendations(containerId, options = {}) {
    const { limit = 8, strategy = 'weighted', postId = null } = options;
    const container = document.getElementById(containerId);
    if (!container) return;

    container.innerHTML = `
        <div class="text-center py-3">
            <div class="spinner-border text-white" role="status">
                <span class="visually-hidden">Đang tải...</span>
            </div>
        </div>
    `;

    let url = `/goiy-ai/api/recommendations/?limit=${limit}&strategy=${strategy}`;
    if (postId) url += `&post_id=${postId}`;

    fetch(url)
        .then(response => response.json())
        .then(data => {
            if (data.success && data.recommendations.length > 0) {
                renderRecommendations(container, data.recommendations);
            } else {
                container.closest('.recommendations-section').style.display = 'none';
            }
        })
        .catch(error => {
            console.error('Error:', error);
            container.closest('.recommendations-section').style.display = 'none';
        });
}

function renderRecommendations(container, posts) {
    if (!posts || posts.length === 0) return;

    let html = '<div class="row g-3">';
    posts.forEach(post => {
        const imageUrl = post.image_url || '/static/images/no-image.png';
        const priceFormatted = new Intl.NumberFormat('vi-VN').format(post.price);
        const titleShort = post.title.length > 50 ? post.title.substring(0, 50) + '...' : post.title;

        html += `
        <div class="col-lg-3 col-md-4 col-sm-6 mb-3">
            <div class="card h-100 shadow-sm" style="transition: transform 0.2s;" onmouseover="this.style.transform='translateY(-5px)'" onmouseout="this.style.transform='translateY(0)'">
                <img src="${imageUrl}" class="card-img-top" alt="${titleShort}"
                     style="height: 180px; object-fit: cover;">
                <div class="card-body p-3">
                    <h6 class="card-title mb-2">
                        <a href="/room/${post.id}/" class="text-dark text-decoration-none">
                            ${titleShort}
                        </a>
                    </h6>
                    <p class="text-danger fw-bold mb-1">
                        <i class="fas fa-tag"></i> ${priceFormatted} VNĐ
                    </p>
                    <p class="text-muted small mb-2">
                        <i class="fas fa-map-marker-alt"></i> ${post.province}
                    </p>
                </div>
            </div>
        </div>
        `;
    });
    html += '</div>';
    container.innerHTML = html;
}

// Province Carousel
(function() {
    const carousel = document.getElementById('provinceCarousel');
    if (!carousel) return;

    const cards = carousel.querySelectorAll('.province-card');
    const dots = document.querySelectorAll('.carousel-dot');
    let currentIndex = 0;
    const totalSlides = cards.length;
    let autoSlideInterval;

    function updateCarousel() {
        // Update grid layout based on current index
        const gridTemplates = [
            '2fr 1fr 1fr 1fr 1fr',  // 0 is large
            '1fr 2fr 1fr 1fr 1fr',  // 1 is large
            '1fr 1fr 2fr 1fr 1fr',  // 2 is large
            '1fr 1fr 1fr 2fr 1fr',  // 3 is large
            '1fr 1fr 1fr 1fr 2fr'   // 4 is large
        ];
        carousel.style.gridTemplateColumns = gridTemplates[currentIndex];

        // Update dots
        dots.forEach((dot, index) => {
            dot.style.background = index === currentIndex ? '#1e293b' : '#cbd5e1';
            dot.style.width = index === currentIndex ? '24px' : '8px';
        });
    }

    function nextSlide() {
        currentIndex = (currentIndex + 1) % totalSlides;
        updateCarousel();
    }

    function goToSlide(index) {
        currentIndex = index;
        updateCarousel();
        resetAutoSlide();
    }

    function startAutoSlide() {
        autoSlideInterval = setInterval(nextSlide, 2000);
    }

    function resetAutoSlide() {
        clearInterval(autoSlideInterval);
        startAutoSlide();
    }

    // Dot click handlers
    dots.forEach((dot, index) => {
        dot.addEventListener('click', () => goToSlide(index));
    });

    // Pause on hover
    carousel.addEventListener('mouseenter', () => clearInterval(autoSlideInterval));
    carousel.addEventListener('mouseleave', startAutoSlide);

    // Start auto slide
    startAutoSlide();
})();
