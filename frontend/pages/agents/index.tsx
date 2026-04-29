import { useEffect } from "react";
import { useRouter } from "next/router";

export default function DepartmentsRedirectPage() {
  const router = useRouter();

  useEffect(() => {
    const selectedDepartment =
      typeof router.query.department === "string"
        ? router.query.department
        : typeof router.query.agent === "string"
          ? router.query.agent
          : null;

    void router.replace(
      selectedDepartment
        ? { pathname: "/departments", query: { department: selectedDepartment } }
        : { pathname: "/departments" },
    );
  }, [router]);

  return null;
}
