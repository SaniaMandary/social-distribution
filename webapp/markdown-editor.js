import { marked } from "marked"; 


function initMarkdownEditor(contentTypeId, editorId, previewSectionId, switchBtnId, outputId) {
    const contentTypeSelection = document.getElementById(contentTypeId);
    if (!contentTypeSelection) return;

    function toggleMarkdown() {
        const markdownSection = document.getElementById(previewSectionId);
        if (contentTypeSelection.value === 'text/markdown') {
            markdownSection.style.display = 'block'; 
        } else {
            markdownSection.style.display = 'none'; 
            document.getElementById(outputId).innerHTML = ''; 
        }
    }

    document.getElementById(switchBtnId).addEventListener('click', e => {
        e.preventDefault(); 
        const markdownText = document.getElementById(editorId).value; 
        const htmlOutput = marked(markdownText); 
        document.getElementById(outputId).innerHTML = marked(markdownText); 
    }); 

    contentTypeSelection.addEventListener('change', toggleMarkdown); 
    toggleMarkdown(); 

}

window.initMarkDownEditor = initMarkdownEditor; 

document.addEventListener('DOMContentLoaded', function() { 
    initMarkdownEditor('id_content_type', 'id_entry_text', 
    'markdown-section', 'switch-btn', 'markdown-output');
}); 