/**
 * Password Toggle Functionality
 * Adds show/hide password toggle to all password input fields
 */

document.addEventListener('DOMContentLoaded', function() {
    // SVG icons for eye (show) and eye-off (hide)
    const eyeIcon = `
        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
            <circle cx="12" cy="12" r="3"></circle>
        </svg>
    `;
    
    const eyeOffIcon = `
        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path>
            <line x1="1" y1="1" x2="23" y2="23"></line>
        </svg>
    `;

    // Find all password input fields
    const passwordInputs = document.querySelectorAll('input[type="password"]');
    
    passwordInputs.forEach(function(input) {
        // Skip if already wrapped
        if (input.closest('.password-input-wrapper')) {
            return;
        }

        // Create wrapper
        const wrapper = document.createElement('div');
        wrapper.className = 'password-input-wrapper';
        
        // Insert wrapper before the input
        input.parentNode.insertBefore(wrapper, input);
        
        // Move input inside wrapper
        wrapper.appendChild(input);
        
        // Create toggle button
        const toggleBtn = document.createElement('button');
        toggleBtn.type = 'button';
        toggleBtn.className = 'password-toggle-btn';
        toggleBtn.setAttribute('aria-label', 'Show password');
        toggleBtn.innerHTML = eyeIcon;
        
        // Add click handler
        toggleBtn.addEventListener('click', function(e) {
            e.preventDefault();
            
            const currentType = input.getAttribute('type');
            const newType = currentType === 'password' ? 'text' : 'password';
            
            input.setAttribute('type', newType);
            
            // Update icon and aria-label
            if (newType === 'text') {
                toggleBtn.innerHTML = eyeOffIcon;
                toggleBtn.setAttribute('aria-label', 'Hide password');
            } else {
                toggleBtn.innerHTML = eyeIcon;
                toggleBtn.setAttribute('aria-label', 'Show password');
            }
        });
        
        // Add button to wrapper
        wrapper.appendChild(toggleBtn);
    });
});
