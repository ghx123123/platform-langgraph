// reportApi.ts - 教学报告下载 API 服务

export interface ReportStatus {
  status: 'pending' | 'generating' | 'completed' | 'failed';
  progress?: number;
  message?: string;
  download_url?: string;
}

export interface DownloadOptions {
  filename?: string;
  onProgress?: (progress: number) => void;
  onSuccess?: () => void;
  onError?: (error: Error) => void;
}

/**
 * 获取报告生成状态
 * @param sessionId 教学会话ID
 * @returns 报告状态
 */
export async function getReportStatus(sessionId: string): Promise<ReportStatus> {
  const response = await fetch(`/api/teaching/sessions/${sessionId}/report/status`);
  
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `获取报告状态失败: ${response.status}`);
  }
  
  return response.json();
}

/**
 * 下载PDF报告
 * @param sessionId 教学会话ID
 * @param options 下载选项
 * @returns Promise<void>
 */
export async function downloadReport(
  sessionId: string, 
  options: DownloadOptions = {}
): Promise<void> {
  const { filename, onSuccess, onError } = options;
  
  try {
    // 调用后端API获取PDF
    const response = await fetch(`/api/teaching/sessions/${sessionId}/report/pdf`, {
      method: 'GET',
      headers: {
        'Accept': 'application/pdf',
      },
    });
    
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      
      // 处理特定错误状态
      if (response.status === 404) {
        throw new Error('报告不存在或会话未找到');
      } else if (response.status === 400) {
        throw new Error(errorData.detail || '教学尚未完成，无法生成报告');
      } else if (response.status === 500) {
        throw new Error('报告生成失败，请稍后重试');
      } else {
        throw new Error(errorData.detail || `下载失败: ${response.status}`);
      }
    }
    
    // 获取文件blob
    const blob = await response.blob();
    
    // 检查是否是有效的PDF
    if (blob.type !== 'application/pdf' && !blob.type.includes('pdf')) {
      console.warn('[ReportApi] 返回的内容类型不是PDF:', blob.type);
    }
    
    // 创建下载链接
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    
    // 设置文件名
    const contentDisposition = response.headers.get('content-disposition');
    let finalFilename = filename;
    
    if (!finalFilename && contentDisposition) {
      // 从Content-Disposition解析文件名
      const filenameMatch = contentDisposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
      if (filenameMatch) {
        finalFilename = decodeURIComponent(filenameMatch[1].replace(/['"]/g, ''));
      }
    }
    
    // 默认文件名
    if (!finalFilename) {
      const date = new Date().toISOString().split('T')[0];
      finalFilename = `教学报告_${sessionId}_${date}.pdf`;
    }
    
    link.download = finalFilename;
    
    // 触发下载
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    
    // 清理URL对象
    window.URL.revokeObjectURL(url);
    
    // 回调成功
    onSuccess?.();
    
  } catch (error) {
    console.error('[ReportApi] 下载报告失败:', error);
    onError?.(error instanceof Error ? error : new Error('未知错误'));
    throw error;
  }
}

/**
 * 带重试机制的下载
 * @param sessionId 教学会话ID
 * @param options 下载选项
 * @param maxRetries 最大重试次数
 * @param retryDelay 重试延迟(ms)
 */
export async function downloadReportWithRetry(
  sessionId: string,
  options: DownloadOptions = {},
  maxRetries: number = 3,
  retryDelay: number = 1000
): Promise<void> {
  let lastError: Error | null = null;
  
  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      await downloadReport(sessionId, options);
      return; // 成功则直接返回
    } catch (error) {
      lastError = error instanceof Error ? error : new Error('未知错误');
      
      // 如果是用户可处理的错误（如教学未完成），不重试
      if (lastError.message.includes('教学尚未完成') || 
          lastError.message.includes('报告不存在')) {
        throw lastError;
      }
      
      // 最后一次尝试，直接抛出错误
      if (attempt === maxRetries) {
        throw new Error(`下载失败，已重试${maxRetries}次: ${lastError.message}`);
      }
      
      // 等待后重试
      console.log(`[ReportApi] 第${attempt}次下载失败，${retryDelay}ms后重试...`);
      await new Promise(resolve => setTimeout(resolve, retryDelay));
    }
  }
}

/**
 * 检查是否可以下载报告
 * @param sessionStatus 教学会话状态
 * @returns boolean
 */
export function canDownloadReport(sessionStatus: string): boolean {
  return sessionStatus === 'completed';
}

/**
 * 获取下载按钮的提示文本
 * @param sessionStatus 教学会话状态
 * @returns string
 */
export function getDownloadButtonTooltip(sessionStatus: string): string {
  switch (sessionStatus) {
    case 'completed':
      return '下载PDF教学报告';
    case 'teaching':
    case 'designing':
      return '教学进行中，请等待完成后下载';
    case 'pending':
      return '请先开始教学';
    case 'failed':
      return '教学失败，无法生成报告';
    default:
      return '暂不可用';
  }
}

export default {
  getReportStatus,
  downloadReport,
  downloadReportWithRetry,
  canDownloadReport,
  getDownloadButtonTooltip,
};
