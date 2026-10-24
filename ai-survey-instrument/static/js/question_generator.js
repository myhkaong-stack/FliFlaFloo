(() => {
 const el=id=>document.getElementById(id), button=el("generate-questions"), questions=el("survey-questions"), status=el("generator-status");
 if(!button||!questions||!status)return;
 button.addEventListener("click",async()=>{
  const title=el("survey-title").value.trim();
  if(!title){el("survey-title").focus();status.textContent="Please enter a survey title first.";return;}
  if(questions.value.trim()&&!window.confirm("Replace the questions currently in the box with newly generated questions?"))return;
  button.disabled=true;button.textContent="Generating…";status.textContent="Generating based on your selected interview type, format, and language…";
  try{
   const response=await fetch("/api/generate-questions",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({title,description:el("survey-description").value.trim(),interview_type:el("interview-type").value,language:el("survey-language").value,question_style:el("question-style").value,count:Number(el("question-count").value),audience:el("question-audience").value.trim(),focus:el("question-focus").value.trim()})});
   const data=await response.json().catch(()=>({}));if(!response.ok)throw new Error(data.error||"Question generation failed.");
   questions.value=data.questions.join("\n");status.textContent="Generated "+data.count+" questions. Review and edit them below.";questions.scrollIntoView({behavior:"smooth",block:"center"});questions.focus({preventScroll:true});
  }catch(error){status.textContent=error.message||"Could not generate questions. Please try again.";}
  finally{button.disabled=false;button.textContent="✦ Generate questions with AI";}
 });
})();