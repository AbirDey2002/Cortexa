import { Layout } from "@/components/Layout";
import { useParams } from "react-router-dom";

const Index = () => {
  const { usecaseId } = useParams<{ usecaseId?: string }>();
  return <Layout initialUsecaseId={usecaseId} />;
};

export default Index;
