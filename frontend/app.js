const API_BASE = '/api/v1';

// 状态
let workflows = [];
let currentWorkflow = null;
let currentSchema = null;
let currentMasks = {};

// DOM 元素
const apiStatusEl = document.getElementById('api-status');
const workflowListEl = document.getElementById('workflow-list');
const refreshBtnEl = document.getElementById('refresh-btn');
const workflowNameEl = document.getElementById('workflow-name');
const workflowFileEl = document.getElementById('workflow-file');
const uploadBtnEl = document.getElementById('upload-btn');
const uploadResultEl = document.getElementById('upload-result');
const detailSectionEl = document.getElementById('workflow-detail-section');
const detailWorkflowNameEl = document.getElementById('detail-workflow-name');
const maskedFieldsEl = document.getElementById('masked-fields');
const saveMasksBtnEl = document.getElementById('save-masks-btn');
const validateWorkflowBtnEl = document.getElementById('validate-workflow-btn');
const validateResultEl = document.getElementById('validate-result');
const generateBtnEl = document.getElementById('generate-btn');
const generateResultEl = document.getElementById('generate-result');
const deleteWorkflowBtnEl = document.getElementById('delete-workflow-btn');
const deleteModalEl = document.getElementById('delete-modal');
const deleteWorkflowNameEl = document.getElementById('delete-workflow-name');
const confirmDeleteBtnEl = document.getElementById('confirm-delete-btn');
const cancelDeleteBtnEl = document.getElementById('cancel-delete-btn');

// 初始化
async function init() {
    await checkApiStatus();
    await loadWorkflows();
    setupEventListeners();
}

// 检查 API 状态
async function checkApiStatus() {
    try {
        const res = await fetch(`${API_BASE}/health`);
        if (res.ok) {
            apiStatusEl.textContent = '已连接';
            apiStatusEl.className = 'status online';
        } else {
            throw new Error('API not healthy');
        }
    } catch (e) {
        apiStatusEl.textContent = '未连接';
        apiStatusEl.className = 'status offline';
    }
}

// 加载工作流列表
async function loadWorkflows() {
    try {
        workflowListEl.innerHTML = '<div class="loading">加载中...</div>';
        const res = await fetch(`${API_BASE}/data/workflow/list`);
        const data = await res.json();
        workflows = data.workflows || [];
        renderWorkflowList();
    } catch (e) {
        workflowListEl.innerHTML = '<div class="result error">加载失败</div>';
    }
}

// 渲染工作流列表
function renderWorkflowList() {
    if (workflows.length === 0) {
        workflowListEl.innerHTML = '<div class="loading">暂无工作流</div>';
        return;
    }

    workflowListEl.innerHTML = workflows.map(wf => `
        <div class="workflow-item ${currentWorkflow === wf ? 'selected' : ''}" data-workflow="${wf}">
            <h3>${wf}</h3>
            <span class="masked-count">点击查看详情</span>
        </div>
    `).join('');

    // 绑定点击事件
    workflowListEl.querySelectorAll('.workflow-item').forEach(item => {
        item.addEventListener('click', () => {
            selectWorkflow(item.dataset.workflow);
        });
    });
}

// 选择工作流
async function selectWorkflow(workflowId) {
    currentWorkflow = workflowId;
    detailWorkflowNameEl.textContent = workflowId;
    detailSectionEl.style.display = 'block';
    renderWorkflowList();
    await loadSchema(workflowId);
}

// 加载 Schema 和屏蔽字段
async function loadSchema(workflowId) {
    try {
        maskedFieldsEl.innerHTML = '<div class="loading">加载中...</div>';

        // 获取 schema
        const schemaRes = await fetch(`${API_BASE}/data/schema/${workflowId}`);
        if (!schemaRes.ok) throw new Error('Schema not found');
        const schemaData = await schemaRes.json();
        currentSchema = schemaData.exposed_fields || {};

        // 获取 mask 配置
        const maskRes = await fetch(`${API_BASE}/data/workflow/${workflowId}/mask`);
        let masks = {};
        if (maskRes.ok) {
            const maskData = await maskRes.json();
            masks = maskData.masked_fields || {};
        }

        currentMasks = masks;
        renderMaskedFields();
    } catch (e) {
        maskedFieldsEl.innerHTML = '<div class="result error">加载失败: ' + e.message + '</div>';
    }
}

// 渲染屏蔽字段列表
function renderMaskedFields() {
    const fields = Object.entries(currentSchema);

    if (fields.length === 0) {
        maskedFieldsEl.innerHTML = '<div class="loading">暂无暴露字段</div>';
        return;
    }

    maskedFieldsEl.innerHTML = fields.map(([key, field]) => `
        <div class="masked-field-item">
            <input type="checkbox" id="mask-${key}"
                   ${currentMasks[key] ? 'checked' : ''}
                   data-field="${key}">
            <div>
                <div class="field-name">${key}</div>
                <div class="field-path">${field.field_path}</div>
            </div>
        </div>
    `).join('');

    // 绑定变更事件
    maskedFieldsEl.querySelectorAll('input[type="checkbox"]').forEach(cb => {
        cb.addEventListener('change', (e) => {
            const field = e.target.dataset.field;
            if (e.target.checked) {
                currentMasks[field] = true;
            } else {
                delete currentMasks[field];
            }
        });
    });
}

// 上传工作流
async function uploadWorkflow() {
    const name = workflowNameEl.value.trim();
    const file = workflowFileEl.files[0];

    if (!name || !file) {
        showResult(uploadResultEl, '请填写工作流名称并选择文件', 'error');
        return;
    }

    try {
        uploadBtnEl.disabled = true;
        uploadBtnEl.textContent = '上传中...';

        const formData = new FormData();
        formData.append('file', file);

        // 先上传文件
        const res = await fetch(`${API_BASE}/data/workflow/${name}/upload`, {
            method: 'POST',
            body: formData
        });

        if (!res.ok) {
            throw new Error('上传失败');
        }

        showResult(uploadResultEl, '上传成功', 'success');
        workflowNameEl.value = '';
        workflowFileEl.value = '';
        await loadWorkflows();
    } catch (e) {
        showResult(uploadResultEl, '上传失败: ' + e.message, 'error');
    } finally {
        uploadBtnEl.disabled = false;
        uploadBtnEl.textContent = '上传';
    }
}

// 保存屏蔽设置
async function saveMasks() {
    if (!currentWorkflow) return;

    try {
        saveMasksBtnEl.disabled = true;
        saveMasksBtnEl.textContent = '保存中...';

        const res = await fetch(`${API_BASE}/data/workflow/${currentWorkflow}/mask`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                masked_fields: currentMasks
            })
        });

        if (!res.ok) throw new Error('保存失败');

        showResult(maskedFieldsEl.parentElement.querySelector('.result') || maskedFieldsEl,
            '保存成功', 'success');
    } catch (e) {
        showResult(maskedFieldsEl.parentElement.querySelector('.result') || maskedFieldsEl,
            '保存失败: ' + e.message, 'error');
    } finally {
        saveMasksBtnEl.disabled = false;
        saveMasksBtnEl.textContent = '保存屏蔽设置';
    }
}

// 验证工作流
async function validateWorkflow() {
    if (!currentWorkflow) return;

    try {
        validateWorkflowBtnEl.disabled = true;
        validateWorkflowBtnEl.textContent = '检查中...';
        validateResultEl.innerHTML = '';

        const res = await fetch(`${API_BASE}/data/workflow/validate?workflow_id=${currentWorkflow}`, {
            method: 'POST'
        });
        const data = await res.json();

        if (data.status === 'complete') {
            validateResultEl.innerHTML = '<div class="result success">所有依赖完整</div>';
        } else {
            let html = '<div class="result error">';
            html += `<p>${data.message}</p>`;
            if (data.missing && data.missing.length > 0) {
                html += '<ul>';
                data.missing.forEach(m => {
                    html += `<li>${m.type}: ${m.model}</li>`;
                });
                html += '</ul>';
            }
            if (data.download_guide) {
                html += '<p>下载指南:</p><ul>';
                for (const [type, models] of Object.entries(data.download_guide)) {
                    models.forEach(model => {
                        html += `<li>${type}: ${model}</li>`;
                    });
                }
                html += '</ul>';
            }
            html += '</div>';
            validateResultEl.innerHTML = html;
        }
    } catch (e) {
        validateResultEl.innerHTML = '<div class="result error">检查失败: ' + e.message + '</div>';
    } finally {
        validateWorkflowBtnEl.disabled = false;
        validateWorkflowBtnEl.textContent = '检查依赖';
    }
}

// 生成图片
async function generateImage() {
    if (!currentWorkflow) return;

    try {
        generateBtnEl.disabled = true;
        generateBtnEl.textContent = '生成中...';
        generateResultEl.innerHTML = '<div class="result info">正在提交任务...</div>';

        const res = await fetch(`${API_BASE}/createImage`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                workflow_id: currentWorkflow,
                masked_fields: currentMasks
            })
        });

        if (!res.ok) {
            throw new Error('提交失败');
        }

        const data = await res.json();
        const taskId = data.task_id;

        generateResultEl.innerHTML = `<div class="result info">任务已提交，ID: ${taskId}<br>正在等待完成...</div>`;

        // 轮询状态
        await pollTaskStatus(taskId);
    } catch (e) {
        generateResultEl.innerHTML = '<div class="result error">生成失败: ' + e.message + '</div>';
        generateBtnEl.disabled = false;
        generateBtnEl.textContent = '生成图片';
    }
}

// 轮询任务状态
async function pollTaskStatus(taskId) {
    while (true) {
        await new Promise(resolve => setTimeout(resolve, 2000));

        try {
            const res = await fetch(`${API_BASE}/createImage/${taskId}/status`);
            const data = await res.json();

            if (data.status === 'completed') {
                generateResultEl.innerHTML = `<div class="result success">
                    生成完成！<br>
                    图片: ${data.images ? data.images.join(', ') : '无'}<br>
                    Prompt ID: ${data.prompt_id}
                </div>`;
                break;
            } else if (data.status === 'failed') {
                generateResultEl.innerHTML = `<div class="result error">生成失败: ${data.error || '未知错误'}</div>`;
                break;
            } else {
                generateResultEl.innerHTML = `<div class="result info">任务进行中 (${taskId})...</div>`;
            }
        } catch (e) {
            generateResultEl.innerHTML = '<div class="result error">查询状态失败: ' + e.message + '</div>';
            break;
        }
    }

    generateBtnEl.disabled = false;
    generateBtnEl.textContent = '生成图片';
}

// 删除工作流
async function deleteWorkflow() {
    if (!currentWorkflow) return;

    try {
        const res = await fetch(`${API_BASE}/data/workflow/${currentWorkflow}`, {
            method: 'DELETE'
        });

        if (!res.ok) throw new Error('删除失败');

        hideDeleteModal();
        detailSectionEl.style.display = 'none';
        currentWorkflow = null;
        await loadWorkflows();
    } catch (e) {
        alert('删除失败: ' + e.message);
    }
}

// 显示/隐藏删除对话框
function showDeleteModal() {
    deleteWorkflowNameEl.textContent = currentWorkflow;
    deleteModalEl.style.display = 'flex';
}

function hideDeleteModal() {
    deleteModalEl.style.display = 'none';
}

// 显示结果
function showResult(el, message, type) {
    el.innerHTML = `<div class="result ${type}">${message}</div>`;
}

// 绑定事件
function setupEventListeners() {
    refreshBtnEl.addEventListener('click', loadWorkflows);
    uploadBtnEl.addEventListener('click', uploadWorkflow);
    saveMasksBtnEl.addEventListener('click', saveMasks);
    validateWorkflowBtnEl.addEventListener('click', validateWorkflow);
    generateBtnEl.addEventListener('click', generateImage);
    deleteWorkflowBtnEl.addEventListener('click', showDeleteModal);
    confirmDeleteBtnEl.addEventListener('click', deleteWorkflow);
    cancelDeleteBtnEl.addEventListener('click', hideDeleteModal);

    // 点击模态框外部关闭
    deleteModalEl.addEventListener('click', (e) => {
        if (e.target === deleteModalEl) {
            hideDeleteModal();
        }
    });
}

// 启动
init();
