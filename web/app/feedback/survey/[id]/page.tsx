import React from "react";
import SurveyClient from "../surveyClient";

export default function Page({ params }: { params: { id: string } }) {
  return <SurveyClient surveyId={params.id} />;
}
