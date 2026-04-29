import type { GetServerSideProps } from "next";

export const getServerSideProps: GetServerSideProps = async ({ params }) => {
  const operationId = Array.isArray(params?.executionId) ? params?.executionId[0] : params?.executionId;
  return {
    redirect: {
      destination: operationId ? `/runs/${encodeURIComponent(operationId)}` : "/runs",
      permanent: false,
    },
  };
};

export default function ExecutionDetailRedirectPage() {
  return null;
}
