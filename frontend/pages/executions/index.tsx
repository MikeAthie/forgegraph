import type { GetServerSideProps } from "next";

export const getServerSideProps: GetServerSideProps = async ({ query }) => ({
  redirect: {
    destination:
      typeof query.execution === "string" ? `/runs?operation=${encodeURIComponent(query.execution)}` : "/runs",
    permanent: false,
  },
});

export default function ExecutionsRedirectPage() {
  return null;
}
