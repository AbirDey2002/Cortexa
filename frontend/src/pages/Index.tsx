import { ChatPage } from "./ChatPage";
import { useParams, useNavigate } from "react-router-dom";

const Index = () => {
  // Get the usecase ID from the URL parameters
  const { usecaseId } = useParams<{ usecaseId?: string }>();
  
  return <ChatPage initialUsecaseId={usecaseId} />;
};

export default Index;
