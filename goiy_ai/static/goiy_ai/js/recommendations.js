/**
 * Recommendation System - Frontend tracking và display
 */

// Track view khi user xem chi tiết bài đăng
function trackPostView(postId) {
    const viewStartTime = Date.now();

    // Gửi tracking khi user rời trang
    window.addEventListener('beforeunload', function() {
        const duration = Math.floor((Date.now() - viewStartTime) / 1000);

        navigator.sendBeacon(
            `/goiy-ai/track/view/${postId}/`,
            JSON.stringify({ duration: duration })
        );
    });
}

// Track khi user lưu tin
function trackSavePost(postId) {
    return fetch(`/goiy-ai/track/save/${postId}/`, {
        method: 'POST',
        headers: {
            'X-CSRFToken': getCookie('csrftoken'),
            'Content-Type': 'application/json'
        }
    });
}

// Track khi user bỏ lưu tin
function trackUnsavePost(postId) {
    return fetch(`/goiy-ai/track/unsave/${postId}/`, {
        method: 'POST',
        headers: {
            'X-CSRFToken': getCookie('csrftoken'),
            'Content-Type': 'application/json'
        }
    });
}

// Track khi user liên hệ/chat
function trackContact(postId) {
    return fetch(`/goiy-ai/track/contact/${postId}/`, {
        method: 'POST',
        headers: {
            'X-CSRFToken': getCookie('csrftoken'),
            'Content-Type': 'application/json'
        }
    });
}

// Track khi user gửi yêu cầu thuê
function trackRentalRequest(postId) {
    return fetch(`/goiy-ai/track/request/${postId}/`, {
        method: 'POST',
        headers: {
            'X-CSRFToken': getCookie('csrftoken'),
            'Content-Type': 'application/json'
        }
    });
}

// Track tìm kiếm
function trackSearch(filters, resultsCount) {
    return fetch('/goiy-ai/track/search/', {
        method: 'POST',
        headers: {
            'X-CSRFToken': getCookie('csrftoken'),
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            query: filters.query || '',
            category: filters.category || '',
            province_id: filters.province_id || null,
            district_id: filters.district_id || null,
            min_price: filters.min_price || null,
            max_price: filters.max_price || null,
            min_area: filters.min_area || null,
            max_area: filters.max_area || null,
            features: filters.features || [],
            results_count: resultsCount
        })
    });
}

// Load recommendations và hiển thị
function loadRecommendations(containerId, options = {}) {
    const {
        limit = 8,
        strategy = 'weighted',
        postId = null,
        onLoad = null
    } = options;

    const container = document.getElementById(containerId);
    if (!container) return;

    // Show loading
    container.innerHTML = `
        <div class="text-center py-4">
            <div class="spinner-border text-primary" role="status">
                <span class="visually-hidden">Đang tải gợi ý...</span>
            </div>
        </div>
    `;

    // Build URL
    let url = `/goiy-ai/api/recommendations/?limit=${limit}&strategy=${strategy}`;
    if (postId) {
        url += `&post_id=${postId}`;
    }

    // Fetch recommendations
    fetch(url)
        .then(response => response.json())
        .then(data => {
            if (data.success && data.recommendations.length > 0) {
                renderRecommendations(container, data.recommendations);

                if (onLoad) {
                    onLoad(data);
                }
            } else {
                container.innerHTML = '';  // Ẩn nếu không có gợi ý
            }
        })
        .catch(error => {
            console.error('Error loading recommendations:', error);
            container.innerHTML = '';
        });
}

// Render recommendations ra HTML
function renderRecommendations(container, posts) {
    let html = '<div class="row g-3">';

    posts.forEach(post => {
        const imageUrl = post.image_url || '/static/images/no-image.png';
        const priceFormatted = new Intl.NumberFormat('vi-VN').format(post.price);

        html += `
        <div class="col-md-3 col-sm-6 mb-3">
            <div class="card h-100 shadow-sm recommendation-card" data-post-id="${post.id}">
                <img src="${imageUrl}" class="card-img-top" alt="${post.title}"
                     style="height: 180px; object-fit: cover;"
                     onerror="this.src='/static/images/no-image.png'">

                <div class="card-body p-3">
                    <h6 class="card-title mb-2">
                        <a href="/room/${post.id}/" class="text-dark text-decoration-none"
                           onclick="trackPostView(${post.id})">
                            ${truncateText(post.title, 50)}
                        </a>
                    </h6>

                    <p class="text-danger fw-bold mb-2">
                        <i class="fas fa-tag"></i> ${priceFormatted} VNĐ
                    </p>

                    <p class="text-muted small mb-2">
                        <i class="fas fa-map-marker-alt"></i>
                        ${post.district ? post.district + ', ' : ''}${post.province || ''}
                    </p>

                    <p class="text-muted small mb-2">
                        <i class="fas fa-ruler-combined"></i> ${post.area}m²
                    </p>

                    <div class="d-flex justify-content-between align-items-center mt-2">
                        <a href="/room/${post.id}/" class="btn btn-sm btn-primary"
                           onclick="trackPostView(${post.id})">
                            <i class="fas fa-eye"></i> Xem
                        </a>

                        <button class="btn btn-sm btn-outline-danger save-btn"
                                data-post-id="${post.id}"
                                onclick="handleSaveClick(this, ${post.id})">
                            <i class="far fa-heart"></i>
                        </button>
                    </div>
                </div>
            </div>
        </div>
        `;
    });

    html += '</div>';
    container.innerHTML = html;
}

// Handle save/unsave button
function handleSaveClick(button, postId) {
    const icon = button.querySelector('i');
    const isSaved = icon.classList.contains('fas');

    if (isSaved) {
        // Unsave
        trackUnsavePost(postId).then(() => {
            icon.classList.remove('fas');
            icon.classList.add('far');
            button.classList.remove('btn-danger');
            button.classList.add('btn-outline-danger');
        });
    } else {
        // Save
        trackSavePost(postId).then(() => {
            icon.classList.remove('far');
            icon.classList.add('fas');
            button.classList.remove('btn-outline-danger');
            button.classList.add('btn-danger');
        });
    }
}

// Utility: Truncate text
function truncateText(text, maxLength) {
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
}

// Utility: Get CSRF token
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
