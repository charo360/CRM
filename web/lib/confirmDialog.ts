import Swal from "sweetalert2";
import "sweetalert2/dist/sweetalert2.min.css";

type ConfirmOptions = {
  title: string;
  text?: string;
  confirmText?: string;
  cancelText?: string;
};

/** SweetAlert2 confirmation (client-only). */
export async function confirmDialog({
  title,
  text,
  confirmText = "Delete",
  cancelText = "Cancel",
}: ConfirmOptions): Promise<boolean> {
  const result = await Swal.fire({
    title,
    text,
    icon: "warning",
    showCancelButton: true,
    confirmButtonText: confirmText,
    cancelButtonText: cancelText,
    confirmButtonColor: "#dc2626",
    cancelButtonColor: "#64748b",
    reverseButtons: true,
    focusCancel: true,
  });
  return result.isConfirmed === true;
}
