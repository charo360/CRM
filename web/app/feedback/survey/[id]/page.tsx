import React from "react";
import SurveyClient from "../surveyClient";

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <SurveyClient surveyId={id} />;
}
