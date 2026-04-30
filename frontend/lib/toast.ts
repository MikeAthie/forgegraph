import { toast, type ExternalToast } from "sonner";

type ToastOptions = Omit<ExternalToast, "description">;

export const showSuccess = (message: string, description?: string, options?: ToastOptions) => {
  toast.success(message, { ...options, description });
};

export const showError = (message: string, description?: string, options?: ToastOptions) => {
  toast.error(message, { ...options, description });
};

export const showWarning = (message: string, description?: string, options?: ToastOptions) => {
  toast.warning(message, { ...options, description });
};

export const showInfo = (message: string, description?: string, options?: ToastOptions) => {
  toast.info(message, { ...options, description });
};

export const showLoading = (message: string) => {
  return toast.loading(message);
};

export const dismissToast = (toastId: string | number) => {
  toast.dismiss(toastId);
};

export { toast };
