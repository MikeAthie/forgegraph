import { useEffect } from "react";
import { useRouter } from "next/router";

export default function DepartmentsRedirectPage() {
  const router = useRouter();

  const { replace } = router;
  useEffect(() => {
    const selectedDepartment =
      typeof router.query.department === "string"
        ? router.query.department
        : typeof router.query.agent === "string"
          ? router.query.agent
          : null;

    void replace(
      selectedDepartment
        ? { pathname: "/departments", query: { department: selectedDepartment } }
        : { pathname: "/departments" },
    );
  }, [router, replace]);

  return null;
}
