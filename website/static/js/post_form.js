// ===== POST FORM JAVASCRIPT =====
// Tách từ post_form.html để tối ưu performance

// Global variables
let VN = null;
let streetSuggestions = [];
let streetTimer = null;
let geocodeTimer = null;

// DOM Elements
let $province, $district, $ward, $street, $house, $address, $lat, $lng;
let map, marker;

// Constants
const DEFAULT_CENTER = [10.776, 106.700]; // HCM

// ===== INITIALIZATION =====
function initializeElements() {
    $province = document.getElementById('id_province');
    $district = document.getElementById('id_district');
    $ward = document.getElementById('id_ward');
    $street = document.getElementById('id_street');
    $house = document.getElementById('id_houseNumber');
    $address = document.getElementById('id_address');
    $lat = document.getElementById('id_lat');
    $lng = document.getElementById('id_lng');
}

// ===== MAP SETUP =====
function initializeMap() {
    map = L.map('map').setView(DEFAULT_CENTER, 11);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '&copy; OpenStreetMap'
    }).addTo(map);

    marker = L.marker(DEFAULT_CENTER, { draggable: true }).addTo(map);
    marker.on('moveend', (e) => {
        const pos = e.target.getLatLng();
        $lat.value = pos.lat.toFixed(7);
        $lng.value = pos.lng.toFixed(7);
    });
}

// ===== SELECT HELPERS =====
function makeSearchable(selectEl, placeholder) {
    new TomSelect(selectEl, {
        create: false,
        maxOptions: 5000,
        placeholder: placeholder || '',
        allowEmptyOption: true,
        render: { option: (data, escape) => `<div>${escape(data.text)}</div>` }
    });
}

function resetSelect(selectEl) {
    if (selectEl.tomselect) selectEl.tomselect.destroy();
    selectEl.innerHTML = '<option value="">-- Chọn --</option>';
}

function fillOptions(selectEl, items, { useNameAsValue = false, placeholder = '' } = {}) {
    resetSelect(selectEl);
    items.forEach(it => {
        const op = document.createElement('option');
        op.value = useNameAsValue ? it.name : it.id;
        op.textContent = it.name;
        selectEl.appendChild(op);
    });
    makeSearchable(selectEl, placeholder);
}

function getSelectedText(selectEl) {
    const i = selectEl.selectedIndex;
    return i >= 0 ? (selectEl.options[i]?.text || '').trim() : '';
}

// ===== FINDERS =====
function findProvinceById(id) {
    return VN.provinces.find(p => p.id === parseInt(id));
}

function findDistrictById(province, id) {
    return (province?.districts || []).find(d => d.id === parseInt(id));
}

// ===== STREET AUTOCOMPLETE =====
async function searchStreets(query) {
    if (!query || query.length < 2) {
        hideStreetSuggestions();
        return;
    }

    const district = getSelectedText($district);
    const province = getSelectedText($province);

    if (!district || !province) return;

    const searchQuery = `${query}, ${district}, ${province}, Vietnam`;

    try {
        const url = `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(searchQuery)}&addressdetails=1&limit=10&countrycodes=vn`;
        const res = await fetch(url, { headers: { 'Accept-Language': 'vi' } });
        const data = await res.json();

        streetSuggestions = data
            .filter(item => item.address && (item.address.road || item.address.street))
            .map(item => ({
                name: item.address.road || item.address.street,
                display_name: item.display_name
            }))
            .filter((item, index, self) =>
                index === self.findIndex(t => t.name === item.name)
            );

        showStreetSuggestions();
    } catch (e) {
        console.warn('Street search error', e);
    }
}

function showStreetSuggestions() {
    let dropdown = document.getElementById('street-suggestions');
    if (!dropdown) {
        dropdown = document.createElement('div');
        dropdown.id = 'street-suggestions';
        dropdown.style.cssText = `
            position: absolute;
            background: white;
            border: 1px solid #ddd;
            border-radius: 8px;
            max-height: 300px;
            overflow-y: auto;
            z-index: 1000;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            width: 100%;
            margin-top: 2px;
        `;
        $street.parentElement.style.position = 'relative';
        $street.parentElement.appendChild(dropdown);
    }

    dropdown.innerHTML = '';

    if (streetSuggestions.length === 0) {
        dropdown.innerHTML = '<div style="padding: 12px; color: #999;">Không tìm thấy đường phù hợp</div>';
    } else {
        streetSuggestions.forEach(street => {
            const item = document.createElement('div');
            item.style.cssText = `
                padding: 12px;
                cursor: pointer;
                border-bottom: 1px solid #f0f0f0;
                transition: background 0.2s;
            `;
            item.innerHTML = `
                <div style="font-weight: 500; color: #2c3e50;">${street.name}</div>
                <div style="font-size: 0.85em; color: #95a5a6; margin-top: 4px;">${street.display_name}</div>
            `;
            item.addEventListener('mouseenter', () => item.style.background = '#f8f9fa');
            item.addEventListener('mouseleave', () => item.style.background = 'white');
            item.addEventListener('click', () => {
                $street.value = street.name;
                hideStreetSuggestions();
                updateAddressAndGeocode();
            });
            dropdown.appendChild(item);
        });
    }

    dropdown.style.display = 'block';
}

function hideStreetSuggestions() {
    const dropdown = document.getElementById('street-suggestions');
    if (dropdown) dropdown.style.display = 'none';
}

// ===== ADDRESS & GEOCODE =====
function updateAddressAndGeocode() {
    const streetValue = $street.value || '';
    const parts = [
        ($house.value || '').trim(),
        streetValue.trim(),
        getSelectedText($ward),
        getSelectedText($district),
        getSelectedText($province),
        'Việt Nam'
    ].filter(Boolean);
    const addr = parts.join(', ');
    $address.value = addr;

    if (geocodeTimer) clearTimeout(geocodeTimer);
    if (addr) geocodeTimer = setTimeout(() => geocode(addr), 600);
}

async function geocode(query, zoomLevel = 15) {
    try {
        const url = `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(query)}&addressdetails=1&limit=1`;
        const res = await fetch(url, { headers: { 'Accept-Language': 'vi' } });
        const data = await res.json();
        if (Array.isArray(data) && data.length) {
            const { lat, lon } = data[0];
            const latNum = parseFloat(lat), lonNum = parseFloat(lon);
            $lat.value = latNum.toFixed(7);
            $lng.value = lonNum.toFixed(7);
            marker.setLatLng([latNum, lonNum]);
            map.setView([latNum, lonNum], zoomLevel);
        }
    } catch (e) {
        console.warn('Geocode error', e);
    }
}

async function jumpToLocation(locationName, zoomLevel = 12) {
    if (!locationName) return;

    try {
        const url = `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(locationName + ', Vietnam')}&addressdetails=1&limit=1`;
        const res = await fetch(url, { headers: { 'Accept-Language': 'vi' } });
        const data = await res.json();
        if (Array.isArray(data) && data.length) {
            const { lat, lon } = data[0];
            const latNum = parseFloat(lat), lonNum = parseFloat(lon);
            map.setView([latNum, lonNum], zoomLevel);
            if ($address.value && $address.value.length > 20) {
                marker.setLatLng([latNum, lonNum]);
                $lat.value = latNum.toFixed(7);
                $lng.value = lonNum.toFixed(7);
            }
        }
    } catch (e) {
        console.warn('Jump to location error', e);
    }
}

// ===== DATA LOAD =====
async function loadData(dataUrl) {
    console.log('🔄 Loading location data from:', dataUrl);
    const res = await fetch(dataUrl);
    VN = await res.json();
    console.log('✅ Loaded provinces:', VN.provinces.length);
    console.log('📍 First 5 provinces:', VN.provinces.slice(0, 5).map(p => `${p.id}. ${p.name}`));

    fillOptions($province, VN.provinces, { useNameAsValue: false, placeholder: 'Tỉnh/Thành phố' });
    console.log('✅ Filled province select with', VN.provinces.length, 'options');

    resetSelect($district); makeSearchable($district, 'Quận/Huyện');
    resetSelect($ward); makeSearchable($ward, 'Phường/Xã');
}

// ===== EVENT HANDLERS =====
function setupProvinceHandler() {
    $province.addEventListener('change', () => {
        const provinceId = $province.value;
        const province = findProvinceById(provinceId);

        fillOptions($district, province ? province.districts : [], { placeholder: 'Quận/Huyện' });
        resetSelect($ward); makeSearchable($ward, 'Phường/Xã');
        $street.value = '';
        hideStreetSuggestions();

        const provinceName = getSelectedText($province);
        if (provinceName) jumpToLocation(provinceName, 11);

        updateAddressAndGeocode();
    });
}

function setupDistrictHandler() {
    $district.addEventListener('change', () => {
        const province = findProvinceById($province.value);
        const district = findDistrictById(province, $district.value);

        fillOptions($ward, district ? district.wards : [], { placeholder: 'Phường/Xã' });
        $street.value = '';
        hideStreetSuggestions();

        const districtName = getSelectedText($district);
        const provinceName = getSelectedText($province);
        if (districtName && provinceName) {
            jumpToLocation(`${districtName}, ${provinceName}`, 13);
        }

        updateAddressAndGeocode();
    });
}

function setupWardHandler() {
    $ward.addEventListener('change', () => {
        const wardName = getSelectedText($ward);
        const districtName = getSelectedText($district);
        const provinceName = getSelectedText($province);
        if (wardName && districtName && provinceName) {
            jumpToLocation(`${wardName}, ${districtName}, ${provinceName}`, 14);
        }
        updateAddressAndGeocode();
    });
}

function setupStreetHandler() {
    $street.addEventListener('input', function () {
        const query = this.value.trim();
        if (streetTimer) clearTimeout(streetTimer);
        streetTimer = setTimeout(() => searchStreets(query), 400);
        updateAddressAndGeocode();
    });
}

function setupHouseHandler() {
    $house.addEventListener('input', updateAddressAndGeocode);
}

function setupClickOutsideHandler() {
    document.addEventListener('click', function (e) {
        if (!$street.contains(e.target) && !document.getElementById('street-suggestions')?.contains(e.target)) {
            hideStreetSuggestions();
        }
    });
}

// ===== FILE INPUT UI =====
function setupFileInputs() {
    const imageInput = document.getElementById('image-input');
    if (imageInput) {
        imageInput.addEventListener('change', function () {
            const label = this.nextElementSibling.querySelector('span');
            const fileCount = this.files.length;
            if (fileCount > 0) {
                label.textContent = `Đã chọn ${fileCount} ảnh`;
                this.nextElementSibling.style.background = 'var(--accent)';
                this.nextElementSibling.style.color = 'white';
            }
        });
    }

    const videoInput = document.getElementById('video-input');
    if (videoInput) {
        videoInput.addEventListener('change', function () {
            const label = this.nextElementSibling.querySelector('span');
            if (this.files.length > 0) {
                label.textContent = `Đã chọn: ${this.files[0].name}`;
                this.nextElementSibling.style.background = 'var(--accent)';
                this.nextElementSibling.style.color = 'white';
            }
        });
    }
}

// ===== AUTO RESIZE TEXTAREA =====
function autoResize(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = textarea.scrollHeight + 'px';
}

function setupTextareaAutoResize() {
    const descriptionTextarea = document.getElementById('id_description');
    if (descriptionTextarea) {
        descriptionTextarea.addEventListener('input', function () {
            autoResize(this);
        });
        autoResize(descriptionTextarea);
    }
}

// ===== MAIN INITIALIZATION =====
function initPostForm(dataUrl) {
    initializeElements();
    initializeMap();
    setupProvinceHandler();
    setupDistrictHandler();
    setupWardHandler();
    setupStreetHandler();
    setupHouseHandler();
    setupClickOutsideHandler();
    setupFileInputs();
    setupTextareaAutoResize();
    loadData(dataUrl);
}

// Export for use in HTML
window.initPostForm = initPostForm;
